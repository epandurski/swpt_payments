from swpt_payments import actors as a

D_ID = -1
C_ID = 1


def test_create_formal_offer(db_session):
    a.create_formal_offer(
        payee_creditor_id=C_ID,
        offer_announcement_id=1,
        debtor_ids=[D_ID],
        debtor_amounts=[1000],
        valid_until_ts='2019-12-31T00:00:00Z',
        description=None,
        reciprocal_payment_debtor_id=-2,
        reciprocal_payment_amount=200,
    )


def test_cancel_formal_offer(db_session):
    a.cancel_formal_offer(
        payee_creditor_id=C_ID,
        offer_id=1,
        offer_secret='qwer',
    )


def test_make_payment_order(db_session):
    a.make_payment_order(
        payee_creditor_id=C_ID,
        offer_id=1,
        offer_secret='qwer',
        payer_creditor_id=2,
        payer_payment_order_seqnum=1,
        debtor_id=D_ID,
        amount=1000,
        proof_secret='asdf',
        payer_note={}
    )


def test_on_prepared_payment_transfer_signal(db_session):
    a.on_prepared_payment_transfer_signal(
        debtor_id=D_ID,
        sender_creditor_id=2,
        transfer_id=1,
        coordinator_type='payment',
        recipient_creditor_id=C_ID,
        sender_locked_amount=1000,
        prepared_at_ts='2019-10-01T00:00:00Z',
        coordinator_id=C_ID,
        coordinator_request_id=1,
    )


def test_on_rejected_payment_transfer_signal(db_session):
    a.on_rejected_payment_transfer_signal(
        coordinator_type='payment',
        coordinator_id=C_ID,
        coordinator_request_id=1,
        details={'error_code': '123456', 'message': 'Oops!'},
    )
