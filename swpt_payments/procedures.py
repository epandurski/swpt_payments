import os
from datetime import datetime, timezone
from typing import Optional, List, TypeVar, Callable
from .extensions import db
from .models import FormalOffer, CreatedFormalOfferSignal, PaymentOrder, FinalizePreparedTransferSignal, \
    CanceledFormalOfferSignal, PrepareTransferSignal, FailedPaymentSignal, MIN_INT64, MAX_INT64

T = TypeVar('T')
atomic: Callable[[T], T] = db.atomic


@atomic
def create_formal_offer(payee_creditor_id: int,
                        offer_announcement_id: int,
                        debtor_ids: List[int],
                        debtor_amounts: List[int],
                        valid_until_ts: datetime,
                        description: Optional[dict] = None,
                        reciprocal_payment_debtor_id: Optional[int] = None,
                        reciprocal_payment_amount: int = 0) -> None:
    assert MIN_INT64 <= payee_creditor_id <= MAX_INT64
    assert MIN_INT64 <= offer_announcement_id <= MAX_INT64
    assert len(debtor_ids) == len(debtor_amounts)
    assert all(MIN_INT64 <= debtor_id <= MAX_INT64 for debtor_id in debtor_ids)
    assert all(0 <= debtor_amount <= MAX_INT64 for debtor_amount in debtor_amounts)
    assert reciprocal_payment_debtor_id is None or MIN_INT64 <= reciprocal_payment_debtor_id <= MAX_INT64
    assert 0 <= reciprocal_payment_amount <= MAX_INT64

    offer_secret = os.urandom(18)
    fo = FormalOffer(
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
    db.session.add(fo)
    db.session.flush()
    db.session.add(CreatedFormalOfferSignal(
        payee_creditor_id=payee_creditor_id,
        offer_id=fo.offer_id,
        offer_announcement_id=offer_announcement_id,
        offer_secret=offer_secret,
        offer_created_at_ts=fo.created_at_ts,
    ))


@atomic
def cancel_formal_offer(payee_creditor_id: int, offer_id: int, offer_secret: bytes) -> None:
    fo = FormalOffer.query.filter_by(
        payee_creditor_id=payee_creditor_id,
        offer_id=offer_id,
        offer_secret=offer_secret,
    ).with_for_update().one_or_none()
    if fo:
        pending_payment_orders = PaymentOrder.query.filter_by(
            payee_creditor_id=payee_creditor_id,
            offer_id=offer_id,
            finalized_at_ts=None,
        ).with_for_update().all()
        for payement_order in pending_payment_orders:
            _cancel_payment_order(payement_order)
        db.session.add(CanceledFormalOfferSignal(
            payee_creditor_id=payee_creditor_id,
            offer_id=offer_id,
        ))
        db.session.delete(fo)


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
        fo = FormalOffer.query.filter_by(
            payee_creditor_id=payee_creditor_id,
            offer_id=offer_id,
            offer_secret=offer_secret,
        ).with_for_update(read=True).one_or_none()

        if not fo:
            return failure(
                error_code='PAY001',
                message='The formal offer does not exist.',
            )
        if debtor_id is None or debtor_id not in fo.debtor_ids:
            return failure(
                error_code='PAY002',
                message='Invalid debtor ID.',
            )
        if (debtor_id, amount) not in zip(fo.debtor_ids, _sanitize_amounts(fo.debtor_amounts)):
            return failure(
                error_code='PAY003',
                message='Invalid amount.',
            )
        _create_payment_order(
            fo,
            payer_creditor_id,
            payer_payment_order_seqnum,
            debtor_id,
            amount,
            payer_note,
            proof_secret,
        )


def _create_payment_order(
        fo: FormalOffer,
        payer_creditor_id: int,
        payer_payment_order_seqnum: int,
        debtor_id: int,
        amount: int,
        payer_note: dict,
        proof_secret: bytes) -> None:
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
    with db.retry_on_integrity_error():
        db.session.add(payment_order)
    db.session.add(PrepareTransferSignal(
        payee_creditor_id=fo.payee_creditor_id,
        coordinator_request_id=payment_order.payment_coordinator_request_id,
        min_amount=amount,
        max_amount=amount,
        debtor_id=debtor_id,
        sender_creditor_id=payer_creditor_id,
        recipient_creditor_id=fo.payee_creditor_id,
    ))


def _cancel_payment_order(po: PaymentOrder) -> None:
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
    if po.reciprocal_payment_transfer_id is not None:
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
        details=dict(
            error_code='PAY004',
            message='The formal offer has been canceled.',
        ),
    ))
    po.finalized_at_ts = datetime.now(tz=timezone.utc)
    po.payer_note = None
    po.proof_secret = None


def _sanitize_amounts(amounts: List[Optional[int]]) -> List[int]:
    return [(x if (x is not None and x >= 0) else 0) for x in amounts]
