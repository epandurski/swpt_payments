import datetime
import dramatiq
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql.expression import func, null, or_
from .extensions import db, broker, MAIN_EXCHANGE_NAME


def get_now_utc():
    return datetime.datetime.now(tz=datetime.timezone.utc)


class Signal(db.Model):
    __abstract__ = True

    queue_name = None

    @property
    def event_name(self):  # pragma: no cover
        model = type(self)
        return f'on_{model.__tablename__}'

    def send_signalbus_message(self):  # pragma: no cover
        model = type(self)
        if model.queue_name is None:
            assert not hasattr(model, 'actor_name'), \
                'SignalModel.actor_name is set, but SignalModel.queue_name is not'
            actor_name = self.event_name
            routing_key = f'events.{actor_name}'
        else:
            actor_name = model.actor_name
            routing_key = model.queue_name
        data = model.__marshmallow_schema__.dump(self)
        message = dramatiq.Message(
            queue_name=model.queue_name,
            actor_name=actor_name,
            args=(),
            kwargs=data,
            options={},
        )
        broker.publish_message(message, exchange=MAIN_EXCHANGE_NAME, routing_key=routing_key)


class FormalOffer(db.Model):
    STATUS_INVALID_FLAG = 1

    payee_creditor_id = db.Column(
        db.BigInteger,
        primary_key=True,
        comment='The payee, also the one that is responsible to supply the goods or services.',
    )
    offer_id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='Along with `payee_creditor_id` uniquely identifies the offer.',
    )
    offer_secret = db.Column(
        pg.BYTEA,
        nullable=False,
        comment='A random sequence of bytes that the potential payer should know in order to '
                'view the offer or make a payment.',
    )
    debtor_ids = db.Column(
        pg.ARRAY(db.BigInteger, dimensions=1),
        nullable=False,
        comment='The payment should go through one of these debtors. Each element in this array '
                'must have a corresponding element in the `debtor_amounts` array. Note that'
                'the database schema allows some or all of the elements to be `None`, which '
                'should be handled with care.',
    )
    debtor_amounts = db.Column(
        pg.ARRAY(db.BigInteger, dimensions=1),
        nullable=False,
        comment='Each element in this array must have a corresponding element in the '
                '`debtor_ids` array. Note that the database schema allows one debtor ID to '
                'occur more than once in the `debtor_ids` array, each time with a different '
                'corresponding amount. The payer is expected to transfer one of the amounts '
                'corresponding to the chosen debtor. Also note that the database schema allows '
                'some or all of the `debtor_amounts` elements to be `None` or a negative '
                'number, which should be handled as if they were zeros.',
    )
    description = db.Column(
        pg.JSON,
        comment='A more or less detailed description of the goods or services that will be '
                'supplied if a payment is made to the offer. `NULL` means that the payee will '
                'compensate the payer by making a reciprocal payment. In this case, and only '
                'in this case, the `reciprocal_payment_debtor_id` column can be set to a '
                'non-NULL value.',
    )
    reciprocal_payment_debtor_id = db.Column(
        db.BigInteger,
        comment='The ID of the debtor through which the reciprocal payment will go.',
    )
    reciprocal_payment_amount = db.Column(
        db.BigInteger,
        nullable=False,
        server_default=db.text('0'),
        comment='The amount to be transferred in the reciprocate payment.',
    )
    status = db.Column(
        db.SmallInteger,
        nullable=False,
        default=0,
        comment='Additional offer status flags.',
    )
    valid_until_ts = db.Column(
        db.TIMESTAMP(timezone=True),
        comment='The offer will not be valid after this deadline.'
    )
    created_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False, default=get_now_utc)
    __table_args__ = (
        db.CheckConstraint(func.array_ndims(debtor_ids) == 1),
        db.CheckConstraint(func.array_ndims(debtor_amounts) == 1),
        db.CheckConstraint(func.cardinality(debtor_ids) == func.cardinality(debtor_amounts)),
        db.CheckConstraint(or_(
            description == null(),
            reciprocal_payment_debtor_id == null(),
        )),
        db.CheckConstraint(or_(
            reciprocal_payment_debtor_id != null(),
            reciprocal_payment_amount == 0,
        )),
        db.CheckConstraint(reciprocal_payment_amount >= 0),
        {
            'comment': 'Represents an offer to supply some goods or services for a stated price.',
        }
    )


class PaymentProof(db.Model):
    payee_creditor_id = db.Column(
        db.BigInteger,
        primary_key=True,
        comment='The payee, also the one that is responsible to supply the goods or services.',
    )
    proof_id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='Along with `payee_creditor_id` uniquely identifies the payment proof.',
    )
    proof_secret = db.Column(
        pg.BYTEA,
        nullable=False,
        comment='A random sequence of bytes that the interested party should know in order to '
                'view the payment proof.',
    )
    payer_creditor_id = db.Column(
        db.BigInteger,
        nullable=False,
        comment='The payer.',
    )
    offer_description = db.Column(
        pg.JSON,
        nullable=False,
        comment='An exact copy of the `formal_offer.description` column.',
    )
    debtor_id = db.Column(
        db.BigInteger,
        nullable=False,
        comment='The ID of the debtor through which the payment went. Must be one of the values '
                'in the `offer.debtor_ids` array.',
    )
    amount = db.Column(
        db.BigInteger,
        nullable=False,
        comment='The transferred amount. Must be equal to the corresponding value in the '
                '`offer.debtor_amounts` array.',
    )
    paid_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False, default=get_now_utc)
    __table_args__ = (
        db.CheckConstraint(amount >= 0),
        {
            'comment': 'Represents an evidence that a payment has been made to an offer. '
                       '(The corresponding offer is deleted.)',
        }
    )

    # TODO: Add swapping columns?


class PaymentOrder(db.Model):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_id = db.Column(db.BigInteger, primary_key=True)
    payer_payment_order_id = db.Column(db.BigInteger, primary_key=True)

    # TODO: PreparedTransfers


class CreatedFormalOfferSignal(Signal):
    # These fields are taken from `FormalOffer`.
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_id = db.Column(db.BigInteger, primary_key=True)
    status = db.Column(db.SmallInteger, nullable=False)
    created_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False)

    payee_offer_announcement_id = db.Column(db.BigInteger, nullable=False)


class CanceledFormalOfferSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_id = db.Column(db.BigInteger, primary_key=True)


class SuccessfulPaymentSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    successful_payment_signal_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    offer_id = db.Column(db.BigInteger, nullable=False)
    payer_creditor_id = db.Column(db.BigInteger, nullable=False)
    payer_payment_order_id = db.Column(db.BigInteger, nullable=False)
    debtor_id = db.Column(db.BigInteger, nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    paid_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False)
    proof_id = db.Column(db.BigInteger)
    proof_secret = db.Column(pg.BYTEA)
    __table_args__ = (
        db.CheckConstraint(or_(
            proof_secret != null(),
            proof_id == null(),
        )),
    )


class FailedPaymentSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    failed_payment_signal_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    offer_id = db.Column(db.BigInteger, nullable=False)
    payer_creditor_id = db.Column(db.BigInteger, nullable=False)
    payer_payment_order_id = db.Column(db.BigInteger, nullable=False)
    details = db.Column(pg.JSON, nullable=False, default={})
