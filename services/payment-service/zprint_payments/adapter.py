import hashlib
import hmac
import json
from typing import Protocol
from sqlalchemy import select
from zprint.models import MockTransaction, uid


class PaymentProvider(Protocol):
    def initiate_charge(self, db, merchant_ref: str, amount: int, provider: str): ...
    def verify_transaction(self, db, merchant_ref: str): ...
    def parse_verified_webhook(self, body: bytes, signature: str) -> str: ...
    def query_status(self, db, merchant_ref: str): ...
    def refund(self, db, merchant_ref: str, amount: int): ...


class SimulatedGateway:
    def __init__(self, secret):
        self.secret = secret.encode()

    def initiate_charge(self, db, merchant_ref, amount, provider):
        tx = MockTransaction(merchant_ref=merchant_ref, provider_ref="mock-" + uid(), amount_ugx=amount, provider=provider)
        db.add(tx)
        db.flush()
        return tx

    def verify_transaction(self, db, merchant_ref):
        return db.scalar(select(MockTransaction).where(MockTransaction.merchant_ref == merchant_ref))

    query_status = verify_transaction

    def sign(self, body):
        return hmac.new(self.secret, body, hashlib.sha256).hexdigest()

    def parse_verified_webhook(self, body, signature):
        if not hmac.compare_digest(self.sign(body), signature):
            raise ValueError("Invalid webhook signature")
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("merchant_ref"), str):
            raise ValueError("Invalid webhook payload")
        return data["merchant_ref"]

    def refund(self, db, merchant_ref, amount):
        raise NotImplementedError("Refunds require an authorized recovery workflow in a later phase")
