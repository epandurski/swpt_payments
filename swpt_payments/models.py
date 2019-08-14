import datetime
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql.expression import func
from .extensions import db


def get_now_utc():
    return datetime.datetime.now(tz=datetime.timezone.utc)


class Offer(db.Model):
    creditor_id = db.Column(
        db.BigInteger,
        primary_key=True,
        comment='The payee, also the one that is responsible to supply the goods or services.',
    )
    offer_id = db.Column(
        pg.BYTEA(length=12),
        primary_key=True,
        comment='A random sequence of bytes. Along with `creditor_id` uniquely identifies the '
                'offer. Should be impossible to guess.',
    )
    details = db.Column(pg.JSON, nullable=False)
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
                'corresponding amount. The payer is expected to transfer one of the amounts  '
                'corresponding to the chosen debtor. Also note that the database schema allows '
                'some or all of the `debtor_amounts` elements to be `None` or a negative '
                'number, which should be handled as if they were zeros. ',
    )
    offer_deadline_ts = db.Column(
        db.TIMESTAMP(timezone=True),
        nullable=True,
        comment='The offer will not be valid after this deadline.'
    )
    created_at_ts = db.Column(db.TIMESTAMP(timezone=True), nullable=False, default=get_now_utc)
    __table_args__ = (
        db.CheckConstraint(func.length(offer_id) == 12),
        db.CheckConstraint(func.array_ndims(debtor_ids) == 1),
        db.CheckConstraint(func.array_ndims(debtor_amounts) == 1),
        db.CheckConstraint(func.cardinality(debtor_ids) == func.cardinality(debtor_amounts)),
        {
            'comment': 'Represents a  proposal to supply some goods or services for a given price.'
        }
    )


# TODO: Payment, PreparedTransfer
