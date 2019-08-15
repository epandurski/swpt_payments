"""empty message

Revision ID: b4a7125a8a5a
Revises: b7c5e3b387bc
Create Date: 2019-08-15 16:13:25.492904

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b4a7125a8a5a'
down_revision = 'b7c5e3b387bc'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('failed_payment_signal',
    sa.Column('payee_creditor_id', sa.BigInteger(), nullable=False),
    sa.Column('signal_id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('payer_creditor_id', sa.BigInteger(), nullable=False),
    sa.Column('payer_payment_request_id', sa.BigInteger(), nullable=False),
    sa.Column('offer_key', postgresql.BYTEA(length=12), nullable=False),
    sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('payee_creditor_id', 'signal_id')
    )
    op.create_table('successful_payment_signal',
    sa.Column('payee_creditor_id', sa.BigInteger(), nullable=False),
    sa.Column('proof_key', postgresql.BYTEA(length=12), nullable=False),
    sa.Column('payer_creditor_id', sa.BigInteger(), nullable=False),
    sa.Column('debtor_id', sa.BigInteger(), nullable=False),
    sa.Column('amount', sa.BigInteger(), nullable=False),
    sa.Column('paid_at_ts', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('payer_payment_request_id', sa.BigInteger(), nullable=False),
    sa.Column('offer_key', postgresql.BYTEA(length=12), nullable=False),
    sa.PrimaryKeyConstraint('payee_creditor_id', 'proof_key')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('successful_payment_signal')
    op.drop_table('failed_payment_signal')
    # ### end Alembic commands ###
