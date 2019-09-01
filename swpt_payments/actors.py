from typing import Optional, List
from datetime import datetime
from base64 import urlsafe_b64decode
import iso8601
from .extensions import broker, APP_QUEUE_NAME
from . import procedures


@broker.actor(queue_name=APP_QUEUE_NAME)
def create_formal_offer(
        payee_creditor_id: int,
        offer_announcement_id: int,
        offer_secret: str,
        debtor_ids: List[int],
        debtor_amounts: List[int],
        valid_until_ts: Optional[datetime] = None,
        description: Optional[dict] = None,
        reciprocal_payment_debtor_id: Optional[int] = None,
        reciprocal_payment_amount: int = 0) -> None:

    """Creates a new formal offer.

    `payee_creditor_id` offers to deliver the goods or services
    depicted in `description` if a payment is made to his account via
    one of the debtors in `debtor_ids`, with the corresponding amount
    in `debtor_amounts`. The offer will be valid until
    `valid_until_ts`.

    Before sending a message to this actor, the sender must create a
    Formal Offer (FO) database record, with a primary key of
    `(payee_creditor_id, offer_announcement_id)`, and status
    "initiated". This record will be used to act properly on
    `CreatedFromalOfferSignal` events.

    TODO:

    On received `CreatedFromalOfferSignal`, the status of the
    corresponding FO record must be set to "created", and the received
    value for `offer_id` -- recorded. The "prepared" FO record will
    be, at some point, finalized (either by a
    `SuccessfulPaymentSignal`, or by a `CanceledFormalOfferSignal`, or
    by payment being made to the offer, or by using the
    `cancel_formal_offer` actor), and the status set to
    "finalized". The "finalized" CR record must not be deleted right
    away, to avoid problems when the event handler ends up being
    executed more than once.

    If a `PreparedTransferSignal` is received, but a corresponding CR
    record is not found, the newly prepared transfer must be
    immediately dismissed (by sending a message to the
    `finalize_prepared_transfer` actor with a zero `committed_amount`).

    If a `PreparedTransferSignal` is received for an already
    "prepared" or "finalized" CR record, the corresponding values of
    `debtor_id`, `sender_creditor_id`, and `transfer_id` must be
    compared. If they are the same, no action should be taken. If they
    differ, the newly prepared transfer must be immediately dismissed.

    If a `RejectedTransferSignal` is received, and the status of the
    corresponding CR record is "initiated", the CR record must be
    deleted. Otherwise, no action should be taken.

    """

    procedures.create_formal_offer(
        payee_creditor_id,
        offer_announcement_id,
        urlsafe_b64decode(offer_secret),
        debtor_ids,
        debtor_amounts,
        iso8601.parse_date(valid_until_ts),
        description,
        reciprocal_payment_debtor_id,
        reciprocal_payment_amount,
    )


@broker.actor(queue_name=APP_QUEUE_NAME)
def cancel_formal_offer(
        payee_creditor_id: int,
        offer_id: int) -> None:

    """Cancels an offer."""

    procedures.cancel_formal_offer(
        payee_creditor_id,
        offer_id,
    )


@broker.actor(queue_name=APP_QUEUE_NAME)
def make_payment(
        payee_creditor_id: int,
        offer_id: int,
        payer_creditor_id: int,
        payer_payment_order_seqnum: int,
        debtor_id: int,
        amount: int,
        proof_secret: str,
        payer_note: dict = {}) -> None:

    """Creates a payment order."""

    procedures.make_payment(
        payee_creditor_id,
        offer_id,
        payer_creditor_id,
        payer_payment_order_seqnum,
        debtor_id,
        amount,
        urlsafe_b64decode(proof_secret),
        payer_note,
    )


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
        coordinator_request_id: int) -> None:
    pass


@broker.actor(queue_name=APP_QUEUE_NAME, event_subscription=True)
def on_rejected_payment_transfer_signal(
        debtor_id: int,
        signal_id: int,
        coordinator_type: str,
        coordinator_id: int,
        coordinator_request_id: int,
        details: dict) -> None:
    pass
