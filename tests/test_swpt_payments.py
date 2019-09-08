import pytest
from datetime import datetime, timezone
from swpt_payments import __version__
from swpt_payments import procedures as p
from swpt_payments.models import FormalOffer, CreatedFormalOfferSignal, PaymentOrder, CanceledFormalOfferSignal, \
    FailedPaymentSignal, PrepareTransferSignal, FinalizePreparedTransferSignal, SuccessfulPaymentSignal, \
    PaymentProof


def test_version(db_session):
    assert __version__


D_ID = -1
C_ID = 1
PAYER_NOTE = {'note': 'a note'}
PROOF_SECRET = b'123'
DESCRIPTION = {'message': 'test'}
VALID_UNTIL_TS = datetime(2099, 1, 1, tzinfo=timezone.utc)
OFFER_ANNOUNCEMENT_ID = 4567
PAYER_PAYMENT_ORDER_SEQNUM = 8765
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
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, C_ID + 1,
                         PAYER_PAYMENT_ORDER_SEQNUM, D_ID, 1000, PROOF_SECRET, PAYER_NOTE)
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


def test_make_payment_order_wrong_amount(db_session, offer):
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, C_ID + 1,
                         PAYER_PAYMENT_ORDER_SEQNUM, D_ID, 1001, PROOF_SECRET, PAYER_NOTE)
    assert len(PaymentOrder.query.all()) == 0
    fps = FailedPaymentSignal.query.one()
    assert fps.payee_creditor_id == offer.payee_creditor_id
    assert fps.offer_id == offer.offer_id
    assert fps.payer_creditor_id == C_ID + 1
    assert fps.payer_payment_order_seqnum == PAYER_PAYMENT_ORDER_SEQNUM
    assert fps.details['error_code'] == 'PAY003'


def test_make_payment_order_wrong_debtor(db_session, offer):
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, C_ID + 1,
                         PAYER_PAYMENT_ORDER_SEQNUM, D_ID - 10, 1000, PROOF_SECRET, PAYER_NOTE)
    assert len(PaymentOrder.query.all()) == 0
    fps = FailedPaymentSignal.query.one()
    assert fps.details['error_code'] == 'PAY002'


def test_make_payment_order_wrong_offer(db_session, offer):
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id + 1, offer.offer_secret, C_ID + 1,
                         PAYER_PAYMENT_ORDER_SEQNUM, D_ID, 1000, PROOF_SECRET, PAYER_NOTE)
    assert len(PaymentOrder.query.all()) == 0
    fps = FailedPaymentSignal.query.one()
    assert fps.details['error_code'] == 'PAY001'


def test_make_payment_order_wrong_secret(db_session, offer):
    with pytest.raises(Exception):
        p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, C_ID + 1,
                             PAYER_PAYMENT_ORDER_SEQNUM, D_ID, 1000, None, PAYER_NOTE)


def test_make_payment_order_offer_deadline_passed(db_session):
    deadline = datetime(1900, 1, 1, tzinfo=timezone.utc)
    offer = p.create_formal_offer(
        C_ID, OFFER_ANNOUNCEMENT_ID, [D_ID, D_ID - 1], [AMOUNT1, AMOUNT2], deadline, DESCRIPTION)
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, C_ID + 1,
                         PAYER_PAYMENT_ORDER_SEQNUM, D_ID, 1000, PROOF_SECRET, PAYER_NOTE)
    fps = FailedPaymentSignal.query.one()
    assert fps.details['error_code'] == 'PAY006'
    po = PaymentOrder.query.one()
    po.finalized_at_ts is not None

    # Simulate message re-delivery.
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, C_ID + 1,
                         PAYER_PAYMENT_ORDER_SEQNUM, D_ID, 1000, PROOF_SECRET, PAYER_NOTE)
    assert len(FailedPaymentSignal.query.all()) == 1


def test_make_payment_order(db_session, offer, payment_order):
    fo = offer
    po = payment_order
    assert po.payee_creditor_id == fo.payee_creditor_id
    assert po.offer_id == fo.offer_id
    assert po.payer_creditor_id == C_ID + 1
    assert po.payer_payment_order_seqnum == PAYER_PAYMENT_ORDER_SEQNUM
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

    pts = PrepareTransferSignal.query.one()
    assert pts.payee_creditor_id == po.payee_creditor_id
    assert pts.coordinator_request_id == po.payment_coordinator_request_id
    assert pts.min_amount == pts.max_amount == po.amount
    assert pts.debtor_id == po.debtor_id
    assert pts.sender_creditor_id == po.payer_creditor_id
    assert pts.recipient_creditor_id == po.payee_creditor_id

    p.process_rejected_payment_transfer_signal(
        po.payee_creditor_id, po.payment_coordinator_request_id, {'error_code': '123456'})
    po = PaymentOrder.query.one()
    assert po.finalized_at_ts is not None

    fps = FailedPaymentSignal.query.one()
    assert fps.payee_creditor_id == po.payee_creditor_id
    assert fps.offer_id == offer.offer_id
    assert fps.payer_creditor_id == po.payer_creditor_id
    assert fps.payer_payment_order_seqnum == po.payer_payment_order_seqnum
    assert fps.details['error_code'] == '123456'


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


def test_successful_payment(db_session, offer, payment_order):
    po = payment_order
    coordinator_id = po.payee_creditor_id
    coordinator_request_id = po.payment_coordinator_request_id
    p.process_prepared_payment_transfer_signal(
        po.debtor_id, po.payer_creditor_id, 333, po.payee_creditor_id, AMOUNT1, coordinator_id, coordinator_request_id)
    po = PaymentOrder.query.one()
    if offer.reciprocal_payment_amount == 0:
        po.finalized_at_ts is not None
        fpts = FinalizePreparedTransferSignal.query.one()
        num_prepared_transfers = 1
        assert fpts.payee_creditor_id == po.payee_creditor_id
        assert fpts.debtor_id == po.debtor_id
        assert fpts.sender_creditor_id == po.payer_creditor_id
        assert fpts.transfer_id == 333
        assert fpts.committed_amount == AMOUNT1
        assert fpts.transfer_info['offer_id'] == po.offer_id

        spts = SuccessfulPaymentSignal.query.one()
        assert spts.payee_creditor_id == po.payee_creditor_id
        assert spts.offer_id == po.offer_id
        assert spts.payer_creditor_id == po.payer_creditor_id
        assert spts.payer_payment_order_seqnum == po.payer_payment_order_seqnum
        assert spts.debtor_id == po.debtor_id
        assert spts.amount == po.amount == AMOUNT1
        assert spts.payer_note == PAYER_NOTE
        assert spts.paid_at_ts is not None
        assert spts.reciprocal_payment_debtor_id is None
        assert spts.reciprocal_payment_amount == 0
        assert spts.proof_id is not None
        proof_id = spts.proof_id

    else:
        assert len(PrepareTransferSignal.query.all()) == 2
        num_prepared_transfers = 2
        pts = PrepareTransferSignal.query.filter_by(coordinator_request_id=-coordinator_request_id).one()
        assert pts.payee_creditor_id == po.payee_creditor_id
        assert pts.min_amount == pts.max_amount == po.reciprocal_payment_amount == AMOUNT3
        assert pts.debtor_id == po.reciprocal_payment_debtor_id
        assert pts.sender_creditor_id == po.payee_creditor_id
        assert pts.recipient_creditor_id == po.payer_creditor_id
        p.process_prepared_payment_transfer_signal(
            po.reciprocal_payment_debtor_id, po.payee_creditor_id, 444, po.payer_creditor_id,
            AMOUNT3, coordinator_id, -coordinator_request_id)

        # Message re-deliveries should be fine.
        p.process_prepared_payment_transfer_signal(
            po.reciprocal_payment_debtor_id, po.payee_creditor_id, 444, po.payer_creditor_id,
            AMOUNT3, coordinator_id, -coordinator_request_id)
        p.process_prepared_payment_transfer_signal(
            po.debtor_id, po.payer_creditor_id, 333, po.payee_creditor_id,
            AMOUNT1, coordinator_id, coordinator_request_id)

        po = PaymentOrder.query.one()
        po.finalized_at_ts is not None
        assert len(FinalizePreparedTransferSignal.query.all()) == 2

        fpts = FinalizePreparedTransferSignal.query.filter_by(transfer_id=444).one()
        assert fpts.payee_creditor_id == po.payee_creditor_id
        assert fpts.debtor_id == po.reciprocal_payment_debtor_id
        assert fpts.sender_creditor_id == po.payee_creditor_id
        assert fpts.committed_amount == AMOUNT3
        assert fpts.transfer_info['offer_id'] == po.offer_id

        spts = SuccessfulPaymentSignal.query.one()
        assert spts.payee_creditor_id == po.payee_creditor_id
        assert spts.offer_id == po.offer_id
        assert spts.payer_creditor_id == po.payer_creditor_id
        assert spts.payer_payment_order_seqnum == po.payer_payment_order_seqnum
        assert spts.debtor_id == po.debtor_id
        assert spts.amount == po.amount == AMOUNT1
        assert spts.payer_note == PAYER_NOTE
        assert spts.paid_at_ts is not None
        assert spts.reciprocal_payment_debtor_id is po.reciprocal_payment_debtor_id
        assert spts.reciprocal_payment_amount == po.reciprocal_payment_amount
        assert spts.proof_id is not None
        proof_id = spts.proof_id

    po = PaymentOrder.query.one()
    assert po.payer_note is None
    assert po.proof_secret is None

    pp = PaymentProof.query.one()
    assert pp.payee_creditor_id == po.payee_creditor_id
    assert pp.proof_id == proof_id
    assert pp.proof_secret == PROOF_SECRET
    assert pp.payer_creditor_id == po.payer_creditor_id
    assert pp.debtor_id == po.debtor_id
    assert pp.amount == po.amount
    assert pp.payer_note == PAYER_NOTE
    assert pp.paid_at_ts is not None
    assert pp.reciprocal_payment_debtor_id == offer.reciprocal_payment_debtor_id
    assert pp.reciprocal_payment_amount == offer.reciprocal_payment_amount
    assert pp.offer_id == offer.offer_id
    assert pp.offer_created_at_ts == offer.created_at_ts
    assert pp.offer_description == offer.description

    # Canceling the paid offer should do nothing.
    p.cancel_formal_offer(offer.payee_creditor_id, offer.offer_id, offer.offer_secret)
    assert len(CanceledFormalOfferSignal.query.all()) == 0

    # Process orphan prepared transfer signal.
    p.process_prepared_payment_transfer_signal(
        po.debtor_id, po.payer_creditor_id, 222, po.payee_creditor_id,
        AMOUNT1, coordinator_id, coordinator_request_id)
    assert len(FinalizePreparedTransferSignal.query.all()) == num_prepared_transfers + 1
