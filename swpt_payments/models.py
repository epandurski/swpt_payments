import datetime
import dramatiq
from base64 import urlsafe_b64encode
from marshmallow import Schema, fields
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql.expression import func, null, or_
from .extensions import db, broker, MAIN_EXCHANGE_NAME

MIN_INT32 = -1 << 31
MAX_INT32 = (1 << 31) - 1
MIN_INT64 = -1 << 63
MAX_INT64 = (1 << 63) - 1


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
    payee_creditor_id = db.Column(
        db.BigInteger,
        primary_key=True,
        comment='The payee, also the one that is responsible to supply the goods or services.',
    )
    offer_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
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
                'some or all of the `debtor_amounts` elements to be `None` or negative '
                'numbers, which should be handled as if they were zeros.',
    )
    description = db.Column(
        pg.JSON,
        comment='A more or less detailed description of the goods or services that will be '
                'supplied if a payment is made to the offer. `NULL` means that the payee '
                'has no responsibilities whatsoever.',
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
    valid_until_ts = db.Column(
        db.TIMESTAMP(timezone=True),
        nullable=False,
        comment='The offer will not be valid after this deadline.'
    )
    created_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False, default=get_now_utc)
    __table_args__ = (
        db.CheckConstraint(func.array_ndims(debtor_ids) == 1),
        db.CheckConstraint(func.array_ndims(debtor_amounts) == 1),
        db.CheckConstraint(func.cardinality(debtor_ids) == func.cardinality(debtor_amounts)),
        db.CheckConstraint(reciprocal_payment_amount >= 0),
        db.CheckConstraint(or_(
            reciprocal_payment_debtor_id != null(),
            reciprocal_payment_amount == 0,
        )),
        {
            'comment': 'Represents an offer to supply some goods or services for a stated price.',
        }
    )


class PaymentOrder(db.Model):
    _pcr_seq = db.Sequence('payment_coordinator_request_id_seq', metadata=db.Model.metadata)

    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_id = db.Column(db.BigInteger, primary_key=True)
    payer_creditor_id = db.Column(db.BigInteger, primary_key=True)
    payer_payment_order_seqnum = db.Column(
        db.Integer,
        primary_key=True,
        comment='A number generated by the payer. It is used to distinguish between several '
                'payment orders issued against one offer.',
    )
    debtor_id = db.Column(
        db.BigInteger,
        nullable=False,
        comment='The ID of the debtor through which the payment should go. Must be one of the '
                'values in the `formal_offer.debtor_ids` array.',
    )
    amount = db.Column(
        db.BigInteger,
        nullable=False,
        comment='The amount to be transferred in the payment. Must be equal to the corresponding '
                'value in the `formal_offer.debtor_amounts` array.',
    )
    reciprocal_payment_debtor_id = db.Column(
        db.BigInteger,
        comment='A copy of the corresponding `formal_offer.reciprocal_payment_debtor_id`.',
    )
    reciprocal_payment_amount = db.Column(
        db.BigInteger,
        nullable=False,
        comment='A copy of the corresponding `formal_offer.reciprocal_payment_amount`.',
    )
    payer_note = db.Column(
        pg.JSON,
        nullable=False,
        default={},
        comment='A note from the payer. Can be anything that the payer wants the payee to see.',
    )
    payment_coordinator_request_id = db.Column(
        db.BigInteger,
        nullable=False,
        server_default=_pcr_seq.next_value(),
        comment='This is the value of the `coordinator_request_id` parameter, which has been '
                'sent with the `prepare_transfer` message for the payment. The value of '
                '`payee_creditor_id` is sent as the `coordinator_id` parameter. '
                '`coordinator_type` is "payment".',
    )
    payment_transfer_id = db.Column(
        db.BigInteger,
        comment='This value, along with `debtor_id` and `payer_creditor_id` uniquely identifies '
                'the prepared transfer for the payment.',
    )
    reciprocal_payment_transfer_id = db.Column(
        db.BigInteger,
        comment='When a reciprocal payment is required, this value along with '
                '`reciprocal_payment_debtor_id` and `payee_creditor_id` uniquely identifies'
                'the prepared transfer for the reciprocal payment. The reciprocal payment '
                'should be initiated only after the primary payment has been prepared '
                'successfully. The value of the `coordinator_request_id` parameter for the '
                'reciprocal payment should be `-payment_coordinator_request_id` (always a '
                'negative number). `coordinator_id` should be `payee_creditor_id`. '
                '`coordinator_type` should be "payment".',
    )
    finalized_at_ts = db.Column(db.TIMESTAMP(timezone=True))
    __table_args__ = (
        db.Index(
            'idx_payment_coordinator_request_id',
            payee_creditor_id,
            payment_coordinator_request_id,
            unique=True,
        ),
        db.CheckConstraint(amount >= 0),
        db.CheckConstraint(reciprocal_payment_amount >= 0),
        db.CheckConstraint(payment_coordinator_request_id > 0),
        db.CheckConstraint(or_(
            reciprocal_payment_debtor_id != null(),
            reciprocal_payment_amount == 0,
        )),
        {
            'comment': 'Represents a recent order from a payer to make a payment to an offer.',
        }
    )


class PaymentProof(db.Model):
    payee_creditor_id = db.Column(
        db.BigInteger,
        primary_key=True,
        comment='The payee, also the one that is responsible to supply the goods or services.',
    )
    proof_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
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
    debtor_id = db.Column(
        db.BigInteger,
        nullable=False,
        comment='The ID of the debtor through which the payment went. Must be one of the values '
                'in the `formal_offer.debtor_ids` array.',
    )
    amount = db.Column(
        db.BigInteger,
        nullable=False,
        comment='The transferred amount. Must be equal to the corresponding value in the '
                '`formal_offer.debtor_amounts` array.',
    )
    payer_note = db.Column(
        pg.JSON,
        nullable=False,
        default={},
        comment='A note from the payer. Can be anything that the payer wants the payee to see.',
    )
    paid_at_ts = db.Column(
        db.TIMESTAMP(timezone=True),
        nullable=False,
        default=get_now_utc,
    )
    reciprocal_payment_debtor_id = db.Column(db.BigInteger)
    reciprocal_payment_amount = db.Column(db.BigInteger, nullable=False)
    offer_id = db.Column(db.BigInteger, nullable=False)
    offer_created_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False)
    offer_description = db.Column(pg.JSON)
    __table_args__ = (
        db.CheckConstraint(amount >= 0),
        db.CheckConstraint(reciprocal_payment_amount >= 0),
        db.CheckConstraint(or_(
            reciprocal_payment_debtor_id != null(),
            reciprocal_payment_amount == 0,
        )),
        {
            'comment': 'Represents an evidence that a payment has been made to an offer. '
                       '(The corresponding offer has been deleted.)',
        }
    )


class CreatedFormalOfferSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_id = db.Column(db.BigInteger, primary_key=True)
    offer_announcement_id = db.Column(db.BigInteger, nullable=False)
    offer_secret = db.Column(pg.BYTEA, nullable=False)
    offer_created_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False)

    class __marshmallow__(Schema):
        payee_creditor_id = fields.Integer()
        offer_id = fields.Integer()
        offer_announcement_id = fields.Integer()
        offer_secret = fields.Function(lambda obj: urlsafe_b64encode(obj.offer_secret).decode())
        offer_created_at_ts = fields.DateTime()


class CanceledFormalOfferSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_id = db.Column(db.BigInteger, primary_key=True)


class SuccessfulPaymentSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_id = db.Column(db.BigInteger, primary_key=True)
    payer_creditor_id = db.Column(db.BigInteger, primary_key=True)
    payer_payment_order_seqnum = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.BigInteger, nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    payer_note = db.Column(pg.JSON, nullable=False)
    paid_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False)
    reciprocal_payment_debtor_id = db.Column(db.BigInteger)
    reciprocal_payment_amount = db.Column(db.BigInteger, nullable=False)
    proof_id = db.Column(db.BigInteger, nullable=False)
    __table_args__ = (
        db.CheckConstraint(amount >= 0),
        db.CheckConstraint(reciprocal_payment_amount >= 0),
        db.CheckConstraint(or_(
            reciprocal_payment_debtor_id != null(),
            reciprocal_payment_amount == 0,
        )),
    )


class FailedPaymentSignal(Signal):
    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    offer_id = db.Column(db.BigInteger, primary_key=True)
    payer_creditor_id = db.Column(db.BigInteger, primary_key=True)
    payer_payment_order_seqnum = db.Column(db.Integer, primary_key=True)
    details = db.Column(pg.JSON, nullable=False, default={})


class PrepareTransferSignal(Signal):
    queue_name = 'swpt_accounts'
    actor_name = 'prepare_transfer'

    class __marshmallow__(Schema):
        coordinator_type = fields.String(default='payment')
        payee_creditor_id = fields.Integer(data_key='coordinator_id')
        coordinator_request_id = fields.Integer()
        min_amount = fields.Integer()
        max_amount = fields.Integer()
        debtor_id = fields.Integer()
        sender_creditor_id = fields.Integer()
        recipient_creditor_id = fields.Integer()

    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    coordinator_request_id = db.Column(db.BigInteger, primary_key=True)
    min_amount = db.Column(db.BigInteger, nullable=False)
    max_amount = db.Column(db.BigInteger, nullable=False)
    debtor_id = db.Column(db.BigInteger, nullable=False)
    sender_creditor_id = db.Column(db.BigInteger, nullable=False)
    recipient_creditor_id = db.Column(db.BigInteger, nullable=False)
    __table_args__ = (
        db.CheckConstraint(min_amount > 0),
        db.CheckConstraint(max_amount >= min_amount),
    )


class FinalizePreparedTransferSignal(Signal):
    queue_name = 'swpt_accounts'
    actor_name = 'finalize_prepared_transfer'

    class __marshmallow__(Schema):
        debtor_id = fields.Integer()
        sender_creditor_id = fields.Integer()
        transfer_id = fields.Integer()
        committed_amount = fields.Integer()
        transfer_info = fields.Raw()

    payee_creditor_id = db.Column(db.BigInteger, primary_key=True)
    signal_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    debtor_id = db.Column(db.BigInteger, nullable=False)
    sender_creditor_id = db.Column(db.BigInteger, nullable=False)
    transfer_id = db.Column(db.BigInteger, nullable=False)
    committed_amount = db.Column(db.BigInteger, nullable=False)
    transfer_info = db.Column(pg.JSON, nullable=False)
    __table_args__ = (
        db.CheckConstraint(committed_amount >= 0),
    )
