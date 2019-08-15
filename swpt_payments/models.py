import datetime
import dramatiq
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql.expression import func
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


class Offer(db.Model):
    STATUS_INVALID_FLAG = 1

    payee_creditor_id = db.Column(
        db.BigInteger,
        primary_key=True,
        comment='The payee, also the one that is responsible to supply the goods or services.',
    )
    offer_key = db.Column(
        pg.BYTEA(length=16),
        primary_key=True,
        comment='A random sequence of bytes. Along with `payee_creditor_id` uniquely identifies '
                'the offer. Should be impossible to guess.',
    )
    description = db.Column(
        pg.JSON,
        nullable=False,
        comment='A more or less detailed description of the offer.',
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
    status = db.Column(
        db.SmallInteger,
        nullable=False,
        default=0,
        comment='Additional offer status flags.',
    )
    valid_until_ts = db.Column(
        db.TIMESTAMP(timezone=True),
        nullable=True,
        comment='The offer will not be valid after this deadline.'
    )
    created_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False, default=get_now_utc)
    __table_args__ = (
        db.CheckConstraint(func.length(offer_key) == 16),
        db.CheckConstraint(func.array_ndims(debtor_ids) == 1),
        db.CheckConstraint(func.array_ndims(debtor_amounts) == 1),
        db.CheckConstraint(func.cardinality(debtor_ids) == func.cardinality(debtor_amounts)),
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
    proof_key = db.Column(
        pg.BYTEA(length=16),
        primary_key=True,
        comment='A random sequence of bytes. Along with `payee_creditor_id` uniquely identifies '
                'the payment proof. Should be impossible to guess.',
    )
    payer_creditor_id = db.Column(
        db.BigInteger,
        nullable=False,
        comment='The payer.',
    )
    description = db.Column(
        pg.JSON,
        nullable=False,
        comment='An exact copy of the `offer.description` column.',
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
        db.CheckConstraint(func.length(proof_key) == 16),
        db.CheckConstraint(amount >= 0),
        {
            'comment': 'Represents an evidence that a payment has been made to an offer. '
                       '(The corresponding offer is deleted.)',
        }
    )


# TODO: PreparedTransfer?
# TODO: Document that `offer_announcement_id` is included in the generated `offer_key`.


class CreatedOfferSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_key = db.Column(pg.BYTEA(length=16), primary_key=True)
    payee_announcement_id = db.Column(db.BigInteger, nullable=False)

    # These fields are taken from `Offer`.
    status = db.Column(db.SmallInteger, nullable=False)
    created_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False)


class CanceledOfferSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_key = db.Column(pg.BYTEA(length=16), primary_key=True)


class SuccessfulPaymentSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    payer_creditor_id = db.Column(db.BigInteger, primary_key=True)
    payer_order_id = db.Column(db.BigInteger, primary_key=True)
    offer_key = db.Column(pg.BYTEA(length=16), nullable=False)

    # These fields are taken from `PaymentProof`.
    proof_key = db.Column(pg.BYTEA(length=16), nullable=False)
    debtor_id = db.Column(db.BigInteger, nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    paid_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False)


class FailedPaymentSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    signal_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    payer_creditor_id = db.Column(db.BigInteger, nullable=False)
    payer_order_id = db.Column(db.BigInteger, nullable=False)
    offer_key = db.Column(pg.BYTEA(length=16), nullable=False)
    details = db.Column(pg.JSON, nullable=False, default={})
