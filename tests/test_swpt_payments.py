import pytest
from datetime import datetime, timezone
from swpt_payments import __version__
from swpt_payments import procedures as p
from swpt_payments.models import FormalOffer, CreatedFormalOfferSignal, PaymentOrder, CanceledFormalOfferSignal, \
    FailedPaymentSignal


def test_version(db_session):
    assert __version__


D_ID = -1
C_ID = 1
PAYER_NOTE = {'note': 'a note'}
PROOF_SECRET = b'123'
DESCRIPTION = {'message': 'test'}
VALID_UNTIL_TS = datetime(2099, 1, 1, tzinfo=timezone.utc)
OFFER_ANNOUNCEMENT_ID = 4567
AMOUNT1 = 1000
AMOUNT2 = 2000
AMOUNT3 = 500


@pytest.fixture(params=['simple', 'swap'])
def offer(request):
    if request.param == 'simple':
        return p.create_formal_offer(
            C_ID, OFFER_ANNOUNCEMENT_ID, [D_ID, D_ID - 1], [AMOUNT1, AMOUNT2], VALID_UNTIL_TS, DESCRIPTION)
    elif request.param == 'swap':
        return p.create_formal_offer(
            C_ID, OFFER_ANNOUNCEMENT_ID, [D_ID, D_ID - 1], [AMOUNT1, AMOUNT2], VALID_UNTIL_TS, None, D_ID - 2, AMOUNT3)
    raise Exception()


@pytest.fixture
def payment_order(offer):
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, C_ID + 1, 8765,
                         D_ID, 1000, PROOF_SECRET, PAYER_NOTE)
    return PaymentOrder.query.one()


def test_create_formal_offer(db_session, offer):
    fo = offer
    offers = FormalOffer.query.all()
    assert len(offers) == 1
    assert fo.offer_id == offers[0].offer_id
    assert fo.payee_creditor_id == C_ID
    assert fo.debtor_ids == [D_ID, D_ID - 1]
    assert fo.debtor_amounts == [AMOUNT1, AMOUNT2]
    assert fo.valid_until_ts == VALID_UNTIL_TS
    assert fo.description in [None, DESCRIPTION]
    assert fo.reciprocal_payment_debtor_id in [D_ID - 2, None]
    assert fo.reciprocal_payment_amount in [AMOUNT3, 0]
    assert fo.offer_id is not None
    assert len(fo.offer_secret) > 5
    assert isinstance(fo.created_at_ts, datetime)
    cfos = CreatedFormalOfferSignal.query.one()
    assert cfos.payee_creditor_id == fo.payee_creditor_id
    assert cfos.offer_id == fo.offer_id
    assert cfos.offer_announcement_id == OFFER_ANNOUNCEMENT_ID
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


def test_cancel_formal_offer(db_session, offer, payment_order):
    p.cancel_formal_offer(offer.payee_creditor_id, offer.offer_id, offer.offer_secret)
    cfos = CanceledFormalOfferSignal.query.one()
    assert cfos.payee_creditor_id == offer.payee_creditor_id
    assert cfos.offer_id == offer.offer_id
    po = PaymentOrder.query.one()
    assert po.finalized_at_ts is not None
    fps = FailedPaymentSignal.query.one()
    assert fps.payee_creditor_id == po.payee_creditor_id
    assert fps.offer_id == offer.offer_id
    assert fps.payer_creditor_id == po.payer_creditor_id
    assert fps.payer_payment_order_seqnum == po.payer_payment_order_seqnum
    assert fps.details['error_code'] == 'PAY004'
