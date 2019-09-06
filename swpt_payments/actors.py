from typing import Optional, List
from base64 import urlsafe_b64decode
import iso8601
from .extensions import broker, APP_QUEUE_NAME
from . import procedures


@broker.actor(queue_name=APP_QUEUE_NAME)
def create_formal_offer(
        payee_creditor_id: int,
        offer_announcement_id: int,
        debtor_ids: List[int],
        debtor_amounts: List[int],
        valid_until_ts: str,
        description: Optional[dict] = None,
        reciprocal_payment_debtor_id: Optional[int] = None,
        reciprocal_payment_amount: int = 0) -> None:

    """Creates a new formal offer to supply some goods or services.

    The `payee_creditor_id` offers to deliver the goods or services
    depicted in `description` if a payment is made to his account via
    one of the debtors in `debtor_ids` (with the corresponding amount
    in `debtor_amounts`). The offer will be valid until
    `valid_until_ts`. `offer_announcement_id` is a number generated by
    the payee (who creates the offer), and must be different for each
    offer announced by a given payee.

    If `reciprocal_payment_debtor_id` is not `None`, an automated
    reciprocal transfer (for the `reciprocal_payment_amount`, via this
    debtor) will be made from the payee to the payer when the offer is
    paid. This allows formal offers to be used as a form of currency
    swapping mechanism.

    Before sending a message to this actor, the sender must create a
    Formal Offer (FO) database record, with a primary key of
    `(payee_creditor_id, offer_announcement_id)`, and status
    "initiated". This record will be used to act properly on
    `CreatedFromalOfferSignal`, `SuccessfulPaymentSignal`, and
    `CanceledFormalOfferSignal` events.


    CreatedFromalOfferSignal
    ------------------------

    If a `CreatedFromalOfferSignal` is received for an "initiated" FO
    record, the status of the FO record must be set to "created", and
    the received values for `offer_id` and `offer_secret` -- recorded.

    If a `CreatedFromalOfferSignal` is received for an already
    "created", "paid", or "canceled" FO record, the corresponding
    values of `offer_id` must be compared. If they are the same, no
    action should be taken. If they differ, the newly created offer
    must be immediately canceled (by sending a message to the
    `cancel_formal_offer` actor).

    If a `CreatedFromalOfferSignal` is received, but a corresponding
    FO record is not found, the newly created offer must be
    immediately canceled.


    SuccessfulPaymentSignal
    -----------------------

    If a `SuccessfulPaymentSignal` is received for a "created" FO
    record, the status of the FO record should be set to "paid".

    If a `SuccessfulPaymentSignal` is received in any other case, no
    action should be taken.


    CanceledFormalOfferSignal
    -------------------------

    If a `CanceledFormalOfferSignal` is received for a "created" FO
    record, the status of the FO record must be set to "canceled".

    If a `CanceledFormalOfferSignal` is received in any other case, no
    action should be taken.


    IMPORTANT NOTES:

    1. "initiated" FO records must not be deleted.

    2. "created" FO records must not be deleted, Instead, they could
       be requested to be canceled (by sending a message to the
       `cancel_formal_offer` actor).

    3. "paid" or "canceled" FO records can be deleted whenever
       considered appropriate.

    """

    procedures.create_formal_offer(
        payee_creditor_id,
        offer_announcement_id,
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
        offer_id: int,
        offer_secret: str) -> None:

    """Requests the cancellation of a formal offer.

    If the offer has been successfully canceled, a
    `CanceledFormalOfferSignal` will be sent. If the offer has
    received a payment in the meantime, a `SuccessfulPaymentSignal`
    will be sent instead. Nothing happens if an offer with the given
    `payee_creditor_id`, `offer_id`, and `offer_secret` does not
    exist.

    """

    procedures.cancel_formal_offer(
        payee_creditor_id,
        offer_id,
        urlsafe_b64decode(offer_secret),
    )


@broker.actor(queue_name=APP_QUEUE_NAME)
def make_payment_order(
        payee_creditor_id: int,
        offer_id: int,
        offer_secret: str,
        payer_creditor_id: int,
        payer_payment_order_seqnum: int,
        debtor_id: int,
        amount: int,
        proof_secret: str,
        payer_note: dict = {}) -> None:

    """Tries to make a payment to a formal offer.

    If the payment is successfull, a `SuccessfulPaymentSignal` will be
    sent. If the payment is not successful, a `FailedPaymentSignal`
    will be sent.

    """

    procedures.make_payment_order(
        payee_creditor_id,
        offer_id,
        urlsafe_b64decode(offer_secret),
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
        prepared_at_ts: str,
        coordinator_id: int,
        coordinator_request_id: int) -> None:
    assert coordinator_type == 'payment'
    procedures.process_prepared_payment_transfer_signal(
        debtor_id,
        sender_creditor_id,
        transfer_id,
        recipient_creditor_id,
        sender_locked_amount,
        coordinator_id,
        coordinator_request_id,
    )


@broker.actor(queue_name=APP_QUEUE_NAME, event_subscription=True)
def on_rejected_payment_transfer_signal(
        coordinator_type: str,
        coordinator_id: int,
        coordinator_request_id: int,
        details: dict) -> None:
    assert coordinator_type == 'payment'
    procedures.process_rejected_payment_transfer_signal(
        coordinator_id,
        coordinator_request_id,
        details,
    )
