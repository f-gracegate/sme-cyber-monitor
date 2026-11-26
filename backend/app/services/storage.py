"""Encrypted object storage for incident evidence and generated reports.

Objects are encrypted with the data encryption key before they touch disk, and every key is
prefixed with its organisation so one organisation can never address another's objects.
"""

import re
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_KEY = re.compile(r"^[0-9a-f-]{36}/(evidence|reports)/[0-9a-f]{32}$")
_fernet = Fernet(settings.fernet_key)


class StorageError(Exception):
    pass


def _path(key: str) -> Path:
    if not _KEY.match(key):
        raise StorageError("Invalid object key")
    return Path(settings.storage_dir) / key


def put(org_id: uuid.UUID, kind: str, data: bytes) -> str:
    key = f"{org_id}/{kind}/{uuid.uuid4().hex}"
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_fernet.encrypt(data))
    return key


def get(org_id: uuid.UUID, key: str) -> bytes:
    if not key.startswith(f"{org_id}/"):
        raise StorageError("Object belongs to another organisation")
    try:
        return _fernet.decrypt(_path(key).read_bytes())
    except (OSError, InvalidToken) as exc:
        raise StorageError("Object unavailable") from exc
