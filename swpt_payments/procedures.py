import os
from datetime import datetime, timezone
from typing import Optional, List, TypeVar, Callable
from .extensions import db
from .models import FormalOffer, CreatedFormalOfferSignal, PaymentOrder, FinalizePreparedTransferSignal, \
    CanceledFormalOfferSignal, MIN_INT64, MAX_INT64

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


@atomic
def cancel_formal_offer(payee_creditor_id: int, offer_id: int, offer_secret: bytes) -> None:
    formal_offer = FormalOffer.query.filter_by(
        payee_creditor_id=payee_creditor_id,
        offer_id=offer_id,
        offer_secret=offer_secret,
    ).with_for_update().one_or_none()
    if formal_offer:
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
        db.session.delete(formal_offer)


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
    po.finalized_at_ts = datetime.now(tz=timezone.utc)
