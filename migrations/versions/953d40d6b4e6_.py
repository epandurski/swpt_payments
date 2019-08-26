"""empty message

Revision ID: 953d40d6b4e6
Revises: 
Create Date: 2019-08-26 17:31:53.649393

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.schema import Sequence, CreateSequence, DropSequence


# revision identifiers, used by Alembic.
revision = '953d40d6b4e6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(CreateSequence(Sequence('payment_coordinator_request_id_seq')))


def downgrade():
    op.execute(DropSequence(Sequence('payment_coordinator_request_id_seq')))
