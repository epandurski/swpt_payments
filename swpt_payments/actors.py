from typing import Optional, List
from datetime import datetime
from base64 import urlsafe_b64decode
import iso8601
from .extensions import broker, APP_QUEUE_NAME
from . import procedures


@broker.actor(queue_name=APP_QUEUE_NAME)
def create_formal_offer(
        payee_creditor_id: int,
        payee_offer_announcement_id: int,
        offer_secret: str,
        debtor_ids: List[int],
        debtor_amounts: List[int],
        description: Optional[dict],
        valid_until_ts: Optional[datetime] = None,
        reciprocal_payment_debtor_id: Optional[int] = None,
        reciprocal_payment_amount: int = 0) -> None:

    """Creates a new offer."""

    procedures.create_offer(
        payee_creditor_id,
        payee_offer_announcement_id,
        urlsafe_b64decode(offer_secret),
        debtor_ids,
        debtor_amounts,
        description,
        iso8601.parse_date(valid_until_ts),
        reciprocal_payment_debtor_id,
        reciprocal_payment_amount,
    )


# @broker.actor(queue_name=APP_QUEUE_NAME, event_subscription=True)
# def on_prepared_payment_transfer_signal(
#         debtor_id: int,
#         sender_creditor_id: int,
#         transfer_id: int,
#         coordinator_type: str,
#         recipient_creditor_id: int,
#         sender_locked_amount: int,
#         prepared_at_ts: datetime,
#         coordinator_id: int,
#         coordinator_request_id: int):
#     pass
