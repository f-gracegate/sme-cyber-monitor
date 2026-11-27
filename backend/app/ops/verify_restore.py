"""Verify a restored backup (mandatory security scenario 10).

    RESTORE_DATABASE_URL=postgresql+psycopg://owner:...@host/db \
    RESTORE_APP_DATABASE_URL=postgresql+psycopg://smecm_app:...@host/db \
    MANIFEST=/backups/manifest-<stamp>.txt OBJECTS_DIR=/restore/objects \
    python -m app.ops.verify_restore

Checks that the restored database is at the expected schema version, holds the same records as
when it was backed up, still enforces tenant isolation (RLS on every tenant table, the
application role sees nothing without a tenant context, append-only tables stay append-only),
and that stored objects decrypt with the production data key.
"""

import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, func, select, text

from app.core.config import settings
from app.models import Base


def main() -> int:
    owner = create_engine(os.environ["RESTORE_DATABASE_URL"])
    app = create_engine(os.environ["RESTORE_APP_DATABASE_URL"])
    manifest = Path(os.environ["MANIFEST"]).read_text().splitlines()
    objects = Path(os.environ.get("OBJECTS_DIR", settings.storage_dir))
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(("PASS " if ok else "FAIL ") + message)
        if not ok:
            failures.append(message)

    expected = {
        line.split()[1]: int(line.split()[2]) for line in manifest if line.startswith("rows ")
    }
    version = next(line.split()[1] for line in manifest if line.startswith("alembic "))
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()

    with owner.connect() as conn:
        restored_version = conn.scalar(text("SELECT version_num FROM alembic_version"))
        check(restored_version == version, f"schema version {restored_version} (backup {version})")
        check(restored_version == head, f"schema is at the code's head revision {head}")
        for table, count in expected.items():
            if table not in Base.metadata.tables:  # names come from a file: allow only ours
                check(False, f"unknown table {table!r} in manifest")
                continue
            actual = conn.scalar(select(func.count()).select_from(Base.metadata.tables[table]))
            check(actual == count, f"{table}: {actual} rows (backup {count})")
        tenant_tables = [
            t.name for t in Base.metadata.sorted_tables if "organisation_id" in t.c
        ] + ["organisations", "memberships", "push_devices", "feedback"]
        flags = dict(
            (r[0], (r[1], r[2]))
            for r in conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace"
                )
            )
        )
        missing = [t for t in set(tenant_tables) if flags.get(t) != (True, True)]
        check(not missing, f"row-level security forced on all tenant tables {missing or ''}")

    with app.connect() as conn:
        visible = conn.scalar(text("SELECT count(*) FROM assets"))
        check(visible == 0, f"application role sees {visible} assets without a tenant context")
        for table, verb in (("audit_logs", "DELETE FROM"), ("incident_events", "DELETE FROM")):
            try:
                with conn.begin_nested():
                    conn.execute(text(f"{verb} {table}"))
                check(False, f"{table} is append-only for the application role")
            except Exception:  # noqa: BLE001 - permission denied is the expected outcome
                check(True, f"{table} is append-only for the application role")
        conn.rollback()

    fernet = Fernet(settings.fernet_key)
    files = [p for p in objects.rglob("*") if p.is_file()] if objects.exists() else []
    check(bool(files), f"{len(files)} stored objects restored")
    bad = 0
    for path in files:
        try:
            fernet.decrypt(path.read_bytes())
        except InvalidToken:
            bad += 1
    check(bad == 0, f"all {len(files)} objects decrypt with the data encryption key")

    print("RESTORE DRILL " + ("FAILED" if failures else "PASSED"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
