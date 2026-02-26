#!/usr/bin/env bash
set -euo pipefail

alembic upgrade head
python -m seed.init_seed
