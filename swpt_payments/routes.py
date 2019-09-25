import json
from base64 import urlsafe_b64decode
from marshmallow_sqlalchemy import ModelSchema
from flask import Blueprint, abort
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
    def get(self, payee_creditor_id, offer_id, offer_secret):
        offer_secret = urlsafe_b64decode(offer_secret)
        offer = procedures.get_formal_offer(payee_creditor_id, offer_id, offer_secret) or abort(404)
        offer_json = json.dumps(offer_schema.dump(offer))
        return offer_json, 200, {
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=31536000',
        }


class ProofAPI(MethodView):
    def get(self, payee_creditor_id, proof_id, proof_secret):
        proof_secret = urlsafe_b64decode(proof_secret)
        proof = procedures.get_payment_proof(payee_creditor_id, proof_id, proof_secret) or abort(404)
        proof_json = json.dumps(proof_schema.dump(proof))
        return proof_json, 200, {
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=31536000',
        }


# TODO: Add an endpoint that returns the proof with a JSON Web
#       Signature. Or maybe use the same endpoint to return a JSON-LD
#       proof (https://json-ld.org/) with a signature.


web_api.add_url_rule(
    '/payments/<int:payee_creditor_id>/offers/<int:offer_id>/<offer_secret>/',
    view_func=OfferAPI.as_view('show_offer'),
)
web_api.add_url_rule(
    '/payments/<int:payee_creditor_id>/proofs/<int:proof_id>/<proof_secret>/',
    view_func=ProofAPI.as_view('show_proof'),
)
