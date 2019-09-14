import os
from datetime import datetime, timezone
from typing import Optional, List, Tuple, TypeVar, Callable
from .extensions import db
from .models import FormalOffer, CreatedFormalOfferSignal, PaymentOrder, FinalizePreparedTransferSignal, \
    CanceledFormalOfferSignal, PrepareTransferSignal, FailedPaymentSignal, SuccessfulPaymentSignal, \
    PaymentProof, MIN_INT64, MAX_INT64

T = TypeVar('T')
atomic: Callable[[T], T] = db.atomic


@atomic
def get_formal_offer(payee_creditor_id: int, offer_id: int, offer_secret: bytes) -> FormalOffer:
    return FormalOffer.query.filter_by(
        payee_creditor_id=payee_creditor_id,
        offer_id=offer_id,
        offer_secret=offer_secret,
    ).one_or_none()


@atomic
def get_payment_proof(payee_creditor_id: int, proof_id: int, proof_secret: bytes) -> PaymentProof:
    return PaymentProof.query.filter_by(
        payee_creditor_id=payee_creditor_id,
        proof_id=proof_id,
        proof_secret=proof_secret,
    ).one_or_none()


@atomic
def create_formal_offer(payee_creditor_id: int,
                        offer_announcement_id: int,
                        debtor_ids: List[int],
                        debtor_amounts: List[int],
                        valid_until_ts: datetime,
                        description: Optional[dict] = None,
                        reciprocal_payment_debtor_id: Optional[int] = None,
                        reciprocal_payment_amount: int = 0) -> FormalOffer:
    assert MIN_INT64 <= payee_creditor_id <= MAX_INT64
    assert MIN_INT64 <= offer_announcement_id <= MAX_INT64
    assert len(debtor_ids) == len(debtor_amounts)
    assert all(MIN_INT64 <= debtor_id <= MAX_INT64 for debtor_id in debtor_ids)
    assert all(0 <= debtor_amount <= MAX_INT64 for debtor_amount in debtor_amounts)
    assert reciprocal_payment_debtor_id is None or MIN_INT64 <= reciprocal_payment_debtor_id <= MAX_INT64
    assert 0 <= reciprocal_payment_amount <= MAX_INT64

    offer_secret = os.urandom(18)
    formal_offer = FormalOffer(
        payee_creditor_id=payee_creditor_id,
        offer_secret=offer_secret,
        debtor_ids=debtor_ids,
        debtor_amounts=debtor_amounts,
        valid_until_ts=valid_until_ts,
        description=description,
        reciprocal_payment_debtor_id=reciprocal_payment_debtor_id,
        reciprocal_payment_amount=reciprocal_payment_amount,
        created_at_ts=datetime.now(tz=timezone.utc),
    )
    db.session.add(formal_offer)
    db.session.flush()
    db.session.add(CreatedFormalOfferSignal(
        payee_creditor_id=payee_creditor_id,
        offer_id=formal_offer.offer_id,
        offer_announcement_id=offer_announcement_id,
        offer_secret=offer_secret,
        offer_created_at_ts=formal_offer.created_at_ts,
    ))
    return formal_offer


@atomic
def cancel_formal_offer(payee_creditor_id: int, offer_id: int, offer_secret: bytes) -> None:
    formal_offer = FormalOffer.query.filter_by(
        payee_creditor_id=payee_creditor_id,
        offer_id=offer_id,
        offer_secret=offer_secret,
    ).with_for_update().one_or_none()
    if formal_offer:
        _abort_unfinalized_payment_orders(formal_offer)
        db.session.add(CanceledFormalOfferSignal(
            payee_creditor_id=payee_creditor_id,
            offer_id=offer_id,
        ))
        db.session.delete(formal_offer)


@atomic
def make_payment_order(
        payee_creditor_id: int,
        offer_id: int,
        offer_secret: bytes,
        payer_creditor_id: int,
        payer_payment_order_seqnum: int,
        debtor_id: int,
        amount: int,
        proof_secret: bytes,
        payer_note: dict = {}) -> None:
    assert MIN_INT64 <= payee_creditor_id <= MAX_INT64
    assert MIN_INT64 <= offer_id <= MAX_INT64
    assert MIN_INT64 <= payer_creditor_id <= MAX_INT64
    assert MIN_INT64 <= payer_payment_order_seqnum <= MAX_INT64
    assert proof_secret is not None
    assert payer_note is not None

    def failure(**kw) -> None:
        db.session.add(FailedPaymentSignal(
            payee_creditor_id=payee_creditor_id,
            offer_id=offer_id,
            payer_creditor_id=payer_creditor_id,
            payer_payment_order_seqnum=payer_payment_order_seqnum,
            details=kw,
        ))

    payment_order_query = PaymentOrder.query.filter_by(
        payee_creditor_id=payee_creditor_id,
        offer_id=offer_id,
        payer_creditor_id=payer_creditor_id,
        payer_payment_order_seqnum=payer_payment_order_seqnum,
    )

    # We must make sure that a payment order has not been created
    # already for this request. Normally, this can happen only when
    # the request message has been re-delivered. We should ignore the
    # request in such cases.
    if not db.session.query(payment_order_query.exists()).scalar():
        formal_offer = FormalOffer.query.filter_by(
            payee_creditor_id=payee_creditor_id,
            offer_id=offer_id,
            offer_secret=offer_secret,
        ).with_for_update(read=True).one_or_none()

        if not formal_offer:
            return failure(error_code='PAY001', message='The offer does not exist.')
        if debtor_id is None or debtor_id not in formal_offer.debtor_ids:
            return failure(error_code='PAY002', message='Invalid debtor ID.')
        if (debtor_id, amount) not in zip(formal_offer.debtor_ids, _sanitize_amounts(formal_offer.debtor_amounts)):
            return failure(error_code='PAY003', message='Invalid amount.')
        _make_payment_order(
            formal_offer,
            payer_creditor_id,
            payer_payment_order_seqnum,
            debtor_id,
            amount,
            proof_secret,
            payer_note,
        )


@atomic
def process_rejected_payment_transfer_signal(
        coordinator_id: int,
        coordinator_request_id: int,
        details: dict) -> None:
    po, is_reciprocal_payment = _find_payment_order(coordinator_id, coordinator_request_id)
    if po and po.finalized_at_ts is None:
        if is_reciprocal_payment:
            details = {'error_code': 'PAY005', 'message': 'Can not make a reciprocal payment.'}
        _abort_payment_order(po, abort_reason=details)


@atomic
def process_prepared_payment_transfer_signal(
        debtor_id: int,
        sender_creditor_id: int,
        transfer_id: int,
        recipient_creditor_id: int,
        sender_locked_amount: int,
        coordinator_id: int,
        coordinator_request_id: int) -> None:
    assert MIN_INT64 <= debtor_id <= MAX_INT64
    assert MIN_INT64 <= sender_creditor_id <= MAX_INT64
    assert MIN_INT64 <= transfer_id <= MAX_INT64

    po, is_reciprocal_payment = _find_payment_order(coordinator_id, coordinator_request_id)
    if po:
        if is_reciprocal_payment:
            assert po.reciprocal_payment_debtor_id == debtor_id
            assert po.reciprocal_payment_amount == sender_locked_amount
            assert po.payer_creditor_id == recipient_creditor_id
            assert po.payee_creditor_id == sender_creditor_id
            attr_name = 'reciprocal_payment_transfer_id'
        else:
            assert po.debtor_id == debtor_id
            assert po.amount == sender_locked_amount
            assert po.payer_creditor_id == sender_creditor_id
            assert po.payee_creditor_id == recipient_creditor_id
            attr_name = 'payment_transfer_id'
        attr_value = getattr(po, attr_name)
        if attr_value is None and po.finalized_at_ts is None:
            setattr(po, attr_name, transfer_id)
            _try_to_finalize_payment_order(po)
            return
        if attr_value == transfer_id:
            # Normally, this can happen only when the prepared
            # transfer message has been re-delivered. Therefore, no
            # action should be taken.
            return

    db.session.add(FinalizePreparedTransferSignal(
        payee_creditor_id=coordinator_id,
        debtor_id=debtor_id,
        sender_creditor_id=sender_creditor_id,
        transfer_id=transfer_id,
        committed_amount=0,
        transfer_info={},
    ))


@atomic
def flush_payment_orders(cutoff_ts: datetime) -> int:
    return PaymentOrder.query.filter(PaymentOrder.finalized_at_ts <= cutoff_ts).delete()


@atomic
def flush_payment_proofs(cutoff_ts: datetime) -> int:
    return PaymentProof.query.filter(PaymentProof.paid_at_ts <= cutoff_ts).delete()


def _make_payment_order(
        fo: FormalOffer,
        payer_creditor_id: int,
        payer_payment_order_seqnum: int,
        debtor_id: int,
        amount: int,
        proof_secret: bytes,
        payer_note: dict) -> None:
    payment_order = PaymentOrder(
        payee_creditor_id=fo.payee_creditor_id,
        offer_id=fo.offer_id,
        payer_creditor_id=payer_creditor_id,
        payer_payment_order_seqnum=payer_payment_order_seqnum,
        debtor_id=debtor_id,
        amount=amount,
        reciprocal_payment_debtor_id=fo.reciprocal_payment_debtor_id,
        reciprocal_payment_amount=fo.reciprocal_payment_amount,
        payer_note=payer_note,
        proof_secret=proof_secret,
    )
    if datetime.now(tz=timezone.utc) > fo.valid_until_ts:
        _abort_payment_order(
            payment_order,
            abort_reason={'error_code': 'PAY006', 'message': 'The offer has expired.'},
        )
    with db.retry_on_integrity_error():
        db.session.add(payment_order)
    if payment_order.finalized_at_ts is None:
        _try_to_finalize_payment_order(payment_order)


def _abort_unfinalized_payment_orders(fo: FormalOffer) -> None:
    unfinalized_payment_orders = PaymentOrder.query.filter_by(
        payee_creditor_id=fo.payee_creditor_id,
        offer_id=fo.offer_id,
        finalized_at_ts=None,
    ).with_for_update().all()
    for payement_order in unfinalized_payment_orders:
        _abort_payment_order(
            payement_order,
            abort_reason={'error_code': 'PAY004', 'message': 'The offer has been canceled.'},
        )


def _finalize_payment_order(po: PaymentOrder, current_ts: datetime) -> Tuple[dict, bytes]:
    assert po.finalized_at_ts is None

    payer_note = po.payer_note
    proof_secret = po.proof_secret
    po.payer_note = None
    po.proof_secret = None
    po.finalized_at_ts = current_ts
    return payer_note, proof_secret


def _abort_payment_order(po: PaymentOrder, abort_reason: dict) -> None:
    assert po.finalized_at_ts is None

    if po.payment_transfer_id is not None:
        db.session.add(FinalizePreparedTransferSignal(
            payee_creditor_id=po.payee_creditor_id,
            debtor_id=po.debtor_id,
            sender_creditor_id=po.payer_creditor_id,
            transfer_id=po.payment_transfer_id,
            committed_amount=0,
            transfer_info={},
        ))
    if po.reciprocal_payment_transfer_id is not None:  # pragma: no cover
        # Normally, this should never happen.
        db.session.add(FinalizePreparedTransferSignal(
            payee_creditor_id=po.payee_creditor_id,
            debtor_id=po.reciprocal_payment_debtor_id,
            sender_creditor_id=po.payee_creditor_id,
            transfer_id=po.reciprocal_payment_transfer_id,
            committed_amount=0,
            transfer_info={},
        ))
    db.session.add(FailedPaymentSignal(
        payee_creditor_id=po.payee_creditor_id,
        offer_id=po.offer_id,
        payer_creditor_id=po.payer_creditor_id,
        payer_payment_order_seqnum=po.payer_payment_order_seqnum,
        details=abort_reason,
    ))
    _finalize_payment_order(po, datetime.now(tz=timezone.utc))


def _execute_payment_order(po: PaymentOrder) -> None:
    assert po.finalized_at_ts is None

    # We can be sure that the corresponding formal offer record exist,
    # because at this point `po` is locked and *unfinalized*. The
    # trick is: 1) We finalize all unfinalized payment orders when
    # deleting an offer record; 2) We obtain a shared lock on the
    # offer record when creating a new payment order.
    formal_offer = FormalOffer.query.filter_by(
        payee_creditor_id=po.payee_creditor_id,
        offer_id=po.offer_id,
    ).with_for_update().one()

    # Frist: Finalize all payment orders.
    if po.payment_transfer_id is not None:
        db.session.add(FinalizePreparedTransferSignal(
            payee_creditor_id=po.payee_creditor_id,
            debtor_id=po.debtor_id,
            sender_creditor_id=po.payer_creditor_id,
            transfer_id=po.payment_transfer_id,
            committed_amount=po.amount,
            transfer_info={'offer_id': po.offer_id, 'is_reciprocal_payment': False},
        ))
    if po.reciprocal_payment_transfer_id is not None:
        db.session.add(FinalizePreparedTransferSignal(
            payee_creditor_id=po.payee_creditor_id,
            debtor_id=po.reciprocal_payment_debtor_id,
            sender_creditor_id=po.payee_creditor_id,
            transfer_id=po.reciprocal_payment_transfer_id,
            committed_amount=po.reciprocal_payment_amount,
            transfer_info={'offer_id': po.offer_id, 'is_reciprocal_payment': True},
        ))
    payer_note, proof_secret = _finalize_payment_order(po, datetime.now(tz=timezone.utc))
    _abort_unfinalized_payment_orders(formal_offer)

    # Second: Generate a payment proof.
    payment_proof = PaymentProof(
        payee_creditor_id=po.payee_creditor_id,
        proof_secret=proof_secret,
        payer_creditor_id=po.payer_creditor_id,
        debtor_id=po.debtor_id,
        amount=po.amount,
        payer_note=payer_note,
        paid_at_ts=po.finalized_at_ts,
        reciprocal_payment_debtor_id=po.reciprocal_payment_debtor_id,
        reciprocal_payment_amount=po.reciprocal_payment_amount,
        offer_id=po.offer_id,
        offer_created_at_ts=formal_offer.created_at_ts,
        offer_description=formal_offer.description,
    )
    db.session.add(payment_proof)
    db.session.flush()

    # Third: Send successful payment signal and delete the offer.
    db.session.add(SuccessfulPaymentSignal(
        payee_creditor_id=po.payee_creditor_id,
        offer_id=po.offer_id,
        payer_creditor_id=po.payer_creditor_id,
        payer_payment_order_seqnum=po.payer_payment_order_seqnum,
        debtor_id=po.debtor_id,
        amount=po.amount,
        payer_note=payer_note,
        paid_at_ts=po.finalized_at_ts,
        reciprocal_payment_debtor_id=po.reciprocal_payment_debtor_id,
        reciprocal_payment_amount=po.reciprocal_payment_amount,
        proof_id=payment_proof.proof_id,
    ))
    db.session.delete(formal_offer)


def _try_to_finalize_payment_order(po: PaymentOrder) -> None:
    assert po.finalized_at_ts is None

    should_prepare_transfer = po.payment_transfer_id is None and po.amount > 0
    should_prepare_reciprocal_transfer = po.reciprocal_payment_transfer_id is None and po.reciprocal_payment_amount > 0
    if should_prepare_transfer:
        db.session.add(PrepareTransferSignal(
            payee_creditor_id=po.payee_creditor_id,
            coordinator_request_id=po.payment_coordinator_request_id,
            min_amount=po.amount,
            max_amount=po.amount,
            debtor_id=po.debtor_id,
            sender_creditor_id=po.payer_creditor_id,
            recipient_creditor_id=po.payee_creditor_id,
        ))
    elif should_prepare_reciprocal_transfer:
        db.session.add(PrepareTransferSignal(
            payee_creditor_id=po.payee_creditor_id,
            coordinator_request_id=-po.payment_coordinator_request_id,
            min_amount=po.reciprocal_payment_amount,
            max_amount=po.reciprocal_payment_amount,
            debtor_id=po.reciprocal_payment_debtor_id,
            sender_creditor_id=po.payee_creditor_id,
            recipient_creditor_id=po.payer_creditor_id,
        ))
    else:
        _execute_payment_order(po)


def _sanitize_amounts(amounts: List[Optional[int]]) -> List[int]:
    return [(x if (x is not None and x >= 0) else 0) for x in amounts]


def _find_payment_order(coordinator_id: int, coordinator_request_id: int) -> Tuple[Optional[PaymentOrder], bool]:
    assert MIN_INT64 <= coordinator_id <= MAX_INT64
    assert MIN_INT64 < coordinator_request_id <= MAX_INT64 and coordinator_request_id != 0

    po = PaymentOrder.query.filter_by(
        payee_creditor_id=coordinator_id,
        payment_coordinator_request_id=abs(coordinator_request_id),
    ).with_for_update().one_or_none()
    is_reciprocal_payment = coordinator_request_id < 0
    return po, is_reciprocal_payment
