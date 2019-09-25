import json
import binascii
from base64 import urlsafe_b64decode
from marshmallow_sqlalchemy import ModelSchema
from flask import Blueprint, abort, request
from flask.views import MethodView
from . import procedures
from .models import FormalOffer, PaymentProof


class OfferSchema(ModelSchema):
    class Meta:
        model = FormalOffer
        exclude = ['offer_secret']


class ProofSchema(ModelSchema):
    class Meta:
        model = PaymentProof
        exclude = ['proof_secret']


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
        offer_dict = offer_schema.dump(offer)
        offer_dict['self'] = request.base_url
        return json.dumps(offer_dict), 200, {
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
        proof_dict = proof_schema.dump(proof)
        proof_dict['self'] = request.base_url
        return json.dumps(proof_dict), 200, {
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=31536000',
        }


# TODO: Add an endpoint that returns the proof with a JSON Web
#       Signature. Or maybe use the same endpoint to return a JSON-LD
#       proof (https://json-ld.org/) with a signature.


web_api.add_url_rule(
    '/creditors/<int:payee_creditor_id>/formal-offers/<int:offer_id>',
    view_func=OfferAPI.as_view('show_offer'),
)
web_api.add_url_rule(
    '/creditors/<int:payee_creditor_id>/payment-proofs/<int:proof_id>',
    view_func=ProofAPI.as_view('show_proof'),
)
