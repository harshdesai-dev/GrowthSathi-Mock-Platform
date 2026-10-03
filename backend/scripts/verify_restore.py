"""Read-only, full-row checksum comparison of an isolated local Phase 8 restore.

Use SOURCE_DATABASE_URL and RESTORE_DATABASE_URL. No URLs or row values are printed.
This is synthetic local evidence, not a production restore certification.
"""

import hashlib
import json
import os
from urllib.parse import urlsplit

import psycopg
from psycopg import sql


def snapshot(variable):
    url = os.environ[variable]
    target = urlsplit(url)
    if target.hostname not in {"localhost", "127.0.0.1"} or not target.path.startswith(
        "/growthsathi_phase8_"
    ):
        raise SystemExit("Use only isolated local growthsathi_phase8_ databases.")
    result = {}
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
            for (table,) in cursor.fetchall():
                cursor.execute(
                    sql.SQL("SELECT row_to_json(t)::text FROM {} t").format(sql.Identifier(table))
                )
                rows = sorted(row[0] for row in cursor.fetchall())
                digest = hashlib.sha256("\n".join(rows).encode()).hexdigest()
                result[table] = {"count": len(rows), "sha256": digest}
    return result


if __name__ == "__main__":
    source = snapshot("SOURCE_DATABASE_URL")
    restored = snapshot("RESTORE_DATABASE_URL")
    if source != restored:
        raise SystemExit("RESTORE MISMATCH: do not approve recovery.")
    print(json.dumps({"verified_tables": len(source), "tables": source}, indent=2))
