"""Payment providers.

Paystack is the production provider: it takes Mobile Money (MTN, Telecel, AirtelTigo) and cards
in Ghana cedis through one hosted checkout, so card and wallet details never reach our servers.
The sandbox provider simulates that checkout for development and automated tests.

Every result is checked server-side against the amount and currency we asked for. The browser
redirect is never trusted on its own.
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

log = logging.getLogger("app.billing")


class ProviderError(Exception):
    """The provider could not be reached or rejected the request."""


@dataclass
class Checkout:
    authorization_url: str
    provider_reference: str | None = None


@dataclass
class Verification:
    # success | failed | abandoned | pending
    status: str
    amount_minor: int | None = None
    currency: str | None = None
    provider_reference: str | None = None
    channel: str | None = None
    payment_method: dict = field(default_factory=dict)
    failure_reason: str | None = None


class SandboxProvider:
    """Simulated checkout. Outcomes are recorded through the development-only sandbox endpoint."""

    name = "sandbox"

    def initialize(self, *, reference: str, **_: object) -> Checkout:
        if not settings.is_development:
            raise ProviderError("The sandbox payment provider is for development only.")
        return Checkout(f"{settings.web_base_url}/billing/sandbox?reference={reference}")

    def verify(self, reference: str) -> Verification:
        # The sandbox has no remote state; the sandbox endpoint applies outcomes directly.
        return Verification(status="pending")


class PaystackProvider:
    name = "paystack"

    def __init__(self, secret_key: str | None = None, base_url: str | None = None) -> None:
        self.secret_key = secret_key or settings.paystack_secret_key
        self.base_url = (base_url or settings.paystack_base_url).rstrip("/")

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.secret_key}"},
            timeout=20,
        )

    def initialize(
        self,
        *,
        reference: str,
        email: str,
        amount_minor: int,
        currency: str,
        channel: str,
        callback_url: str,
        metadata: dict,
    ) -> Checkout:
        body = {
            "reference": reference,
            "email": email,
            "amount": amount_minor,
            "currency": currency,
            "channels": ["mobile_money"] if channel == "mobile_money" else ["card"],
            "callback_url": callback_url,
            "metadata": metadata,
        }
        try:
            with self._client() as client:
                resp = client.post("/transaction/initialize", json=body)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Could not reach the payment provider.") from exc
        if resp.status_code >= 400 or not data.get("status"):
            log.warning("paystack initialize failed: %s", data.get("message"))
            raise ProviderError(data.get("message") or "The payment provider declined the request.")
        return Checkout(data["data"]["authorization_url"], data["data"].get("access_code"))

    def verify(self, reference: str) -> Verification:
        try:
            with self._client() as client:
                resp = client.get(f"/transaction/verify/{reference}")
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Could not reach the payment provider.") from exc
        if resp.status_code == 404:
            return Verification(status="pending")
        if resp.status_code >= 400 or not data.get("status"):
            raise ProviderError(data.get("message") or "Could not verify the payment.")
        return parse_paystack_transaction(data["data"])

    def valid_signature(self, raw_body: bytes, signature: str | None) -> bool:
        if not signature or not self.secret_key:
            return False
        expected = hmac.new(self.secret_key.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature)


_STATUS = {"success": "success", "failed": "failed", "abandoned": "abandoned", "reversed": "failed"}


def parse_paystack_transaction(tx: dict) -> Verification:
    auth = tx.get("authorization") or {}
    channel = tx.get("channel")
    method: dict = {}
    if channel == "card":
        method = {
            "brand": (auth.get("card_type") or auth.get("brand") or "card").strip(),
            "last4": auth.get("last4"),
        }
    elif channel == "mobile_money":
        phone = str(auth.get("mobile_money_number") or auth.get("last4") or "")
        method = {"network": auth.get("bank"), "phone": f"*****{phone[-3:]}" if phone else None}
    return Verification(
        status=_STATUS.get(tx.get("status", ""), "pending"),
        amount_minor=tx.get("amount"),
        currency=tx.get("currency"),
        provider_reference=str(tx.get("id")) if tx.get("id") is not None else None,
        channel=channel,
        payment_method={k: v for k, v in method.items() if v},
        failure_reason=tx.get("gateway_response") if tx.get("status") != "success" else None,
    )


def get_provider(name: str | None = None) -> SandboxProvider | PaystackProvider:
    name = name or settings.payment_provider
    if name == "paystack":
        return PaystackProvider()
    if name == "sandbox":
        return SandboxProvider()
    raise ProviderError(f"Unknown payment provider {name!r}.")
