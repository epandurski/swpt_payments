import pytest
from datetime import datetime, timezone
from swpt_payments import __version__
from swpt_payments import procedures as p
from swpt_payments.models import FormalOffer, CreatedFormalOfferSignal, PaymentOrder


def test_version(db_session):
    assert __version__


D_ID = -1
C_ID = 1
PAYER_NOTE = {'note': 'a note'}
PROOF_SECRET = b'123'


@pytest.fixture(params=['simple', 'swap'])
def offer(request):
    valid_until_ts = datetime(2099, 1, 1, tzinfo=timezone.utc)
    if request.param == 'simple':
        return p.create_formal_offer(
            C_ID, 1, [D_ID, D_ID - 1], [1000, 2000], valid_until_ts, {'message': 'test'})
    elif request.param == 'swap':
        return p.create_formal_offer(
            C_ID, 1, [D_ID, D_ID - 1], [1000, 2000], valid_until_ts, None, D_ID - 2, 500)
    raise Exception()


@pytest.fixture
def payment_order(offer):
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, C_ID + 1, 8765,
                         D_ID, 1000, PROOF_SECRET, PAYER_NOTE)
    return PaymentOrder.query.one()


def test_create_formal_offer(db_session):
    now = datetime.now(tz=timezone.utc)
    valid_until_ts = datetime(2099, 1, 1, tzinfo=timezone.utc)
    description = {'message': 'test'}
    p.create_formal_offer(
        C_ID, 4567, [D_ID, D_ID - 1], [1000, 2000], valid_until_ts, description, D_ID - 2, 500)
    offers = FormalOffer.query.all()
    assert len(offers) == 1
    fo = offers[0]
    assert fo.payee_creditor_id == C_ID
    assert fo.debtor_ids == [D_ID, D_ID - 1]
    assert fo.debtor_amounts == [1000, 2000]
    assert fo.valid_until_ts == valid_until_ts
    assert fo.description == description
    assert fo.reciprocal_payment_debtor_id == D_ID - 2
    assert fo.reciprocal_payment_amount == 500
    assert fo.offer_id is not None
    assert len(fo.offer_secret) > 5
    assert fo.created_at_ts >= now
    cfos = CreatedFormalOfferSignal.query.one()
    assert cfos.payee_creditor_id == fo.payee_creditor_id
    assert cfos.offer_id == fo.offer_id
    assert cfos.offer_announcement_id == 4567
    assert cfos.offer_secret == fo.offer_secret
    assert cfos.offer_created_at_ts == fo.created_at_ts


def test_make_payment_order(db_session, offer, payment_order):
    fo = offer
    po = payment_order
    assert po.payee_creditor_id == fo.payee_creditor_id
    assert po.offer_id == fo.offer_id
    assert po.payer_creditor_id == C_ID + 1
    assert po.payer_payment_order_seqnum == 8765
    assert po.debtor_id == D_ID
    assert po.amount == 1000
    assert po.reciprocal_payment_debtor_id == fo.reciprocal_payment_debtor_id
    assert po.reciprocal_payment_amount == fo.reciprocal_payment_amount
    assert po.payer_note == PAYER_NOTE
    assert po.proof_secret == PROOF_SECRET
    assert po.payment_coordinator_request_id > 0
    assert po.payment_transfer_id is None
    assert po.reciprocal_payment_transfer_id is None
    assert po.finalized_at_ts is None
