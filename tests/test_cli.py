import pytest
from datetime import datetime, timezone
from swpt_payments import procedures as p
from swpt_payments.models import PaymentOrder, PaymentProof
from swpt_payments.extensions import db


@pytest.fixture(scope='function')
def offer():
    deadline = datetime(1900, 1, 1, tzinfo=timezone.utc)
    return p.create_formal_offer(1, 2, [3, 4], [1000, 2000], deadline, {'text': 'test'})


@pytest.fixture(scope='function')
def proof(offer):
    payment_proof = PaymentProof(
        payee_creditor_id=offer.payee_creditor_id,
        proof_secret=b'123',
        payer_creditor_id=2,
        debtor_id=3,
        amount=1000,
        payer_note={},
        reciprocal_payment_debtor_id=offer.reciprocal_payment_debtor_id,
        reciprocal_payment_amount=offer.reciprocal_payment_amount,
        offer_id=offer.offer_id,
        offer_created_at_ts=offer.created_at_ts,
        offer_description=offer.description,
    )
    db.session.add(payment_proof)
    db.session.flush()
    return payment_proof


def test_flush_payment_orders(app, db_session, offer):
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, 234, 3456, 3, 1000, b'123', {})
    assert len(PaymentOrder.query.all()) == 1
    runner = app.test_cli_runner()
    result = runner.invoke(args=['swpt_payments', 'flush_payment_orders', '--days', '-10.0'])
    assert '1 ' in result.output
    assert 'deleted' in result.output
    assert len(PaymentOrder.query.all()) == 0


def test_flush_payment_proofs(app, db_session, proof):
    assert len(PaymentProof.query.all()) == 1
    runner = app.test_cli_runner()
    result = runner.invoke(args=['swpt_payments', 'flush_payment_proofs', '--days', '-10.0'])
    assert '1 ' in result.output
    assert 'deleted' in result.output
    assert len(PaymentOrder.query.all()) == 0
