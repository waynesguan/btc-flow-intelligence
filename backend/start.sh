#!/usr/bin/env bash
set -euo pipefail

echo "[backend] waiting for postgres..."
python - <<'PY'
import time
import psycopg2
from config.settings import get_settings

settings = get_settings()
for _ in range(60):
    try:
        psycopg2.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        ).close()
        print("postgres is ready")
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("postgres connection timeout")
PY

alembic upgrade head
python -m seed.init_seed
uvicorn api.main:app --host 0.0.0.0 --port 8000
