from typing import Optional, List
from datetime import datetime
import iso8601
from .extensions import broker, APP_QUEUE_NAME
from . import procedures


@broker.actor(queue_name=APP_QUEUE_NAME)
def create_offer(
        payee_creditor_id: int,
        payee_offer_announcement_id: int,
        debtor_ids: List[int],
        debtor_amounts: List[int],
        description: dict,
        swap_debtor_id: Optional[int],
        swap_amount: int,
        valid_until_ts: Optional[datetime]) -> None:

    """Creates a new offer."""

    procedures.create_offer(
        payee_creditor_id,
        payee_offer_announcement_id,
        description,
        debtor_ids,
        debtor_amounts,
        iso8601.parse_date(valid_until_ts),
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
