"""Encrypted object storage for incident evidence and generated reports.

Objects are encrypted with the data encryption key before they touch disk, and every key is
prefixed with its organisation so one organisation can never address another's objects.
"""

import re
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_KEY = re.compile(r"^[0-9a-f-]{36}/(evidence|reports|exports)/[0-9a-f]{32}$")
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


def delete(org_id: uuid.UUID, key: str) -> None:
    if not key.startswith(f"{org_id}/"):
        raise StorageError("Object belongs to another organisation")
    _path(key).unlink(missing_ok=True)


def delete_organisation(org_id: uuid.UUID) -> int:
    """Erase every stored object of one organisation (evidence, reports, exports)."""
    root = Path(settings.storage_dir) / str(uuid.UUID(str(org_id)))
    removed = 0
    if root.is_dir():
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
                removed += 1
            else:
                path.rmdir()
        root.rmdir()
    return removed
