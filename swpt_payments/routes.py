import binascii
from urllib.parse import urljoin
from base64 import urlsafe_b64decode
from marshmallow import fields, Schema
from marshmallow.utils import missing
from flask import Blueprint, abort, request, current_app
from flask.views import MethodView
from . import procedures

DEBTOR_PATH = '/debtors/{}'
CREDITOR_PATH = '/creditors/{}'
CONTEXT_PATH = '/contexts/{}'
OFFER_PATH = '/formal-offers/{}/{}'
PROOF_PATH = '/payment-proofs/{}/{}'


def _get_debtor_url(debtor_id):
    return urljoin(current_app.config['BASE_URL'], DEBTOR_PATH.format(debtor_id))


def _get_creditor_url(creditor_id):
    return urljoin(current_app.config['BASE_URL'], CREDITOR_PATH.format(creditor_id))


class JsonLdMixin:
    _id = fields.Method('get_id', data_key='@id')
    _type = fields.Method('get_type', data_key='@type')
    _context = fields.Method('get_context', data_key='@context')

    def get_type(self, obj):
        return type(obj).__name__

    def get_context(self, obj):
        filename = self.get_type(obj) + '.jsonld'
        path = CONTEXT_PATH.format(filename)
        return urljoin(current_app.config['BASE_URL'], path)


class OfferSchema(Schema, JsonLdMixin):
    offer_id = fields.Int(data_key='offerId')
    created_at_ts = fields.DateTime(data_key='offerCreatedAt')
    valid_until_ts = fields.DateTime(data_key='offerValidUntil')
    description = fields.Raw(data_key='offerDescription')
    payee = fields.Function(lambda obj: _get_creditor_url(obj.payee_creditor_id))
    paymentOptions = fields.Method('get_payment_options')
    reciprocalPayment = fields.Method('get_reciprocal_payment')

    def get_id(self, obj):
        path = OFFER_PATH.format(obj.payee_creditor_id, obj.offer_id)
        return urljoin(current_app.config['BASE_URL'], path)

    def get_payment_options(self, obj):
        return [{
            '@type': 'PaymentDescription',
            'via': _get_debtor_url(debtor_id),
            'amount': amount or 0,
        } for debtor_id, amount in zip(obj.debtor_ids, obj.debtor_amounts) if debtor_id is not None]

    def get_reciprocal_payment(self, obj):
        if obj.reciprocal_payment_debtor_id is None:
            return missing
        else:
            return {
                '@type': 'PaymentDescription',
                'via': _get_debtor_url(obj.reciprocal_payment_debtor_id),
                'amount': obj.reciprocal_payment_amount,
            }


class ProofSchema(Schema, JsonLdMixin):
    amount = fields.Int(data_key='paidAmount')
    paid_at_ts = fields.DateTime(data_key='paidAt')
    payer_note = fields.Raw(data_key='payerNote')
    offer_id = fields.Int(data_key='offerId')
    offer_description = fields.Raw(data_key='offerDescription')
    offer_created_at_ts = fields.DateTime(data_key='offerCreatedAt')
    paidVia = fields.Function(lambda obj: _get_debtor_url(obj.debtor_id))
    payee = fields.Function(lambda obj: _get_creditor_url(obj.payee_creditor_id))
    payer = fields.Function(lambda obj: _get_creditor_url(obj.payer_creditor_id))
    reciprocalPayment = fields.Method('get_reciprocal_payment')

    def get_id(self, obj):
        path = PROOF_PATH.format(obj.payee_creditor_id, obj.proof_id)
        return urljoin(current_app.config['BASE_URL'], path)

    def get_reciprocal_payment(self, obj):
        if obj.reciprocal_payment_debtor_id is None:
            return missing
        else:
            return {
                '@type': 'PaymentDescription',
                'via': _get_debtor_url(obj.reciprocal_payment_debtor_id),
                'amount': obj.reciprocal_payment_amount,
            }


offer_schema = OfferSchema()
proof_schema = ProofSchema()
web_api = Blueprint('web_api', __name__)


class OfferAPI(MethodView):
    def get(self, payee_creditor_id, offer_id):
        offer = procedures.get_formal_offer(payee_creditor_id, offer_id) or abort(404)
        try:
            urlsafe_b64decode(request.args.get('secret', '')) == offer.offer_secret or abort(403)
        except binascii.Error:
            abort(403)
        return offer_schema.dumps(offer), 200, {
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=31536000',
        }


class ProofAPI(MethodView):
    def get(self, payee_creditor_id, proof_id):
        proof = procedures.get_payment_proof(payee_creditor_id, proof_id) or abort(404)
        try:
            urlsafe_b64decode(request.args.get('secret', '')) == proof.proof_secret or abort(403)
        except binascii.Error:
            abort(403)
        return proof_schema.dumps(proof), 200, {
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=31536000',
        }


# TODO: Add JSON-LD signature (https://json-ld.org/) to the payment
#       proof document.


web_api.add_url_rule(
    OFFER_PATH.format('<int:payee_creditor_id>', '<int:offer_id>'),
    view_func=OfferAPI.as_view('show_offer'),
)
web_api.add_url_rule(
    PROOF_PATH.format('<int:payee_creditor_id>', '<int:proof_id>'),
    view_func=ProofAPI.as_view('show_proof'),
)
