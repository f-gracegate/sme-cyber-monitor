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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
