import json
import pytest
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from swpt_payments import procedures
from swpt_payments.models import PaymentProof
from swpt_payments.extensions import db


@pytest.fixture(scope='function')
def client(app, db_session):
    return app.test_client()


@pytest.fixture(scope='function')
def offer():
    return procedures.create_formal_offer(
        1, 2, [3, 4], [1000, 2000], datetime(2099, 1, 1, tzinfo=timezone.utc), {'text': 'test'})


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


def test_get_offer(client, offer):
    r = client.get(f'/formal-offers/{offer.payee_creditor_id}/{offer.offer_id}/')
    assert r.status_code == 404

    r = client.get(f'/formal-offers/{offer.payee_creditor_id}/{offer.offer_id}/x')
    assert r.status_code == 404

    r = client.get(f'/formal-offers/{offer.payee_creditor_id}/{offer.offer_id}/asdf')
    assert r.status_code == 404

    offer_secret = urlsafe_b64encode(offer.offer_secret).decode()
    r = client.get(f'/formal-offers/{offer.payee_creditor_id}/{offer.offer_id}/{offer_secret}')
    assert r.status_code == 200
    assert r.content_type == 'application/json'
    assert 'max-age=' in r.headers['Cache-Control']
    contents = json.loads(r.data)
    assert contents['@id'].endswith(f'/formal-offers/{offer.payee_creditor_id}/{offer.offer_id}/{offer_secret}')
    assert contents['@type'] == 'FormalOffer'
    assert '@context' in contents
    assert contents['offerDescription'] == offer.description


def test_get_proof(client, proof):
    r = client.get(f'/payment-proofs/{proof.payee_creditor_id}/{proof.proof_id}/')
    assert r.status_code == 404

    r = client.get(f'/payment-proofs/{proof.payee_creditor_id}/{proof.proof_id}/x')
    assert r.status_code == 404

    r = client.get(f'/payment-proofs/{proof.payee_creditor_id}/{proof.proof_id}/asdf')
    assert r.status_code == 404

    proof_secret = urlsafe_b64encode(proof.proof_secret).decode()
    r = client.get(f'/payment-proofs/{proof.payee_creditor_id}/{proof.proof_id}/{proof_secret}')
    assert r.status_code == 200
    assert r.content_type == 'application/json'
    assert 'max-age=' in r.headers['Cache-Control']
    contents = json.loads(r.data)
    assert contents['@id'].endswith(f'/payment-proofs/{proof.payee_creditor_id}/{proof.proof_id}/{proof_secret}')
    assert contents['@type'] == 'PaymentProof'
    assert '@context' in contents
    assert contents['paidAmount'] == proof.amount
