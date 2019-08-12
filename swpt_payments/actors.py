from datetime import datetime
from .extensions import broker, APP_QUEUE_NAME


@broker.actor(queue_name=APP_QUEUE_NAME, event_subscription=True)
def on_prepared_payment_transfer_signal(
        debtor_id: int,
        sender_creditor_id: int,
        transfer_id: int,
        coordinator_type: str,
        recipient_creditor_id: int,
        sender_locked_amount: int,
        prepared_at_ts: datetime,
        coordinator_id: int,
        coordinator_request_id: int):
    pass
