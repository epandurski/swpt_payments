import pytest
from datetime import datetime, timezone
from swpt_payments import procedures as p
from swpt_payments.models import PaymentOrder


D_ID = -1
C_ID = 1


@pytest.fixture(scope='function')
def offer():
    deadline = datetime(1900, 1, 1, tzinfo=timezone.utc)
    return p.create_formal_offer(1, 2, [3, 4], [1000, 2000], deadline, {'text': 'test'})


def test_flush_payment_orders(app, db_session, offer):
    p.make_payment_order(offer.payee_creditor_id, offer.offer_id, offer.offer_secret, 234, 3456, 3, 1000, b'123', {})
    assert len(PaymentOrder.query.all()) == 1
    runner = app.test_cli_runner()
    result = runner.invoke(args=['swpt_payments', 'flush_payment_orders', '--days', '-10.0'])
    assert '1 ' in result.output
    assert 'deleted' in result.output
    assert len(PaymentOrder.query.all()) == 0
