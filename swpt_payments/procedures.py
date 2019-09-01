from datetime import datetime, timezone
from typing import Optional, List, TypeVar, Callable
from .extensions import db
from .models import FormalOffer, CreatedFormalOfferSignal, MIN_INT64, MAX_INT64

T = TypeVar('T')
atomic: Callable[[T], T] = db.atomic


@atomic
def create_formal_offer(payee_creditor_id: int,
                        offer_announcement_id: int,
                        debtor_ids: List[int],
                        debtor_amounts: List[int],
                        valid_until_ts: Optional[datetime] = None,
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

    offer_secret = b''  # TODO: Generate a proper secret here.
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
        created_at_ts=formal_offer.offer_id,
        offer_announcement_id=offer_announcement_id,
    ))


@atomic
def cancel_formal_offer(payee_creditor_id: int, offer_id: int) -> None:
    formal_offer = FormalOffer.get_instance((payee_creditor_id, offer_id))
    if formal_offer:
        pass
