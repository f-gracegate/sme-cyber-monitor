import base64
import hashlib
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_SECRET = "dev-only-insecure-secret-key-change-me"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+psycopg://smecm_app:smecm_app_dev@localhost:5532/smecm"
    migration_database_url: str = (
        "postgresql+psycopg://smecm_owner:smecm_owner_dev@localhost:5532/smecm"
    )
    redis_url: str = "redis://localhost:6479/0"

    secret_key: str = _INSECURE_DEFAULT_SECRET
    data_encryption_key: str = ""

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    mfa_token_ttl_minutes: int = 5
    password_reset_ttl_minutes: int = 30
    invitation_ttl_days: int = 7

    cookie_secure: bool = False
    web_base_url: str = "http://localhost:3810"

    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    seed_admin_username: str = "Admin"
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str | None = None

    brand_product_name: str = "SME Cybersecurity Monitoring"

    # Where the reference endpoint agent is served from (mounted from /agents in development).
    agent_dist_path: str = "/agents/endpoint/smecm_agent.py"

    # Encrypted object storage for evidence and reports. Use a mounted volume or network disk;
    # replace with an S3-compatible backend for multi-server deployments.
    storage_dir: str = "/data/objects"
    max_evidence_bytes: int = 10 * 1024 * 1024

    # Mobile app sessions hold tokens in the phone's secure storage and last longer than web ones.
    mobile_refresh_token_ttl_days: int = 30

    # Push notifications. "log" keeps them in a development outbox; "fcm" sends through Firebase
    # Cloud Messaging (Android and, via APNs, iOS) using a service-account JSON key.
    push_provider: str = "log"
    fcm_project_id: str = ""
    fcm_service_account_file: str = ""
    # Push text appears on lock screens and passes through Google/Apple, so by default it only
    # names the severity and alert title; details are fetched in the app after sign-in.
    push_include_details: bool = False

    # Payments. "sandbox" simulates checkout for development and tests; "paystack" takes Mobile
    # Money (MTN, Telecel, AirtelTigo) and cards in Ghana cedis.
    payment_provider: str = "sandbox"
    paystack_secret_key: str = ""
    paystack_base_url: str = "https://api.paystack.co"
    # Days of service kept after a paid period ends, while reminders go out.
    billing_grace_days: int = 7
    # Annual billing charges this many months for twelve.
    annual_months_charged: int = 10
    billing_contact_email: str = "sales@gracegate.example"
    brand_company_name: str = "GraceGate Technologies"

    # Lets asset verification reach private addresses. Only for isolated test labs.
    allow_private_verification_targets: bool = False

    @property
    def is_development(self) -> bool:
        return self.environment in {"development", "test"}

    @property
    def fernet_key(self) -> bytes:
        if self.data_encryption_key:
            return self.data_encryption_key.encode()
        # Development fallback derived from the signing key. Production requires an explicit key.
        digest = hashlib.sha256(("fernet:" + self.secret_key).encode()).digest()
        return base64.urlsafe_b64encode(digest)

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if not self.is_development:
            if self.secret_key == _INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be a random value of at least 32 characters")
            if not self.data_encryption_key:
                raise ValueError("DATA_ENCRYPTION_KEY is required outside development")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true outside development")
            if self.payment_provider == "sandbox":
                raise ValueError("PAYMENT_PROVIDER=sandbox is for development only")
            if self.payment_provider == "paystack" and not self.paystack_secret_key:
                raise ValueError("PAYSTACK_SECRET_KEY is required when PAYMENT_PROVIDER=paystack")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
