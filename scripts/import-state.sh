#!/usr/bin/env bash
#
# import-state.sh — restore a state bundle produced by export-state.sh.
#
# Restores into the running docker compose stack on this machine:
#   1. Postgres dump → wipes + repopulates the cloudsla database
#   2. ChromaDB collection files → into the chroma_data named volume
#   3. sla_docs/ PDFs → into the project's ./sla_docs/ directory
#
# Usage:
#   ./scripts/import-state.sh <bundle.tar.gz>
#
# Pre-conditions:
#   - The stack must be **stopped** before import (avoids races against
#     Postgres while it's being clobbered). The script enforces this.
#   - At minimum the `postgres` and `chromadb` containers must exist
#     (created via `docker compose up --no-start` if not yet started).
#
# This is DESTRUCTIVE — the existing Postgres database and ChromaDB
# collections are wiped and replaced. The script prints a summary and
# asks for confirmation before doing anything irreversible.
#
set -euo pipefail

# ── Resolve project root ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ── Arg parsing ─────────────────────────────────────────────────────────────
if [ $# -ne 1 ]; then
    echo "Usage: $0 <bundle.tar.gz>" >&2
    exit 1
fi
BUNDLE="$1"
if [ ! -f "$BUNDLE" ]; then
    echo "❌ '$BUNDLE' not found." >&2
    exit 1
fi
BUNDLE="$(cd "$(dirname "$BUNDLE")" && pwd)/$(basename "$BUNDLE")"   # absolutise

# ── Config (matches export-state.sh) ────────────────────────────────────────
PG_USER="${POSTGRES_USER:-user}"
PG_DB="${POSTGRES_DB:-cloudsla}"
COMPOSE_PROJECT="cloudsla-recommender"
PG_CONTAINER="${COMPOSE_PROJECT}-postgres-1"
CHROMA_VOLUME="${COMPOSE_PROJECT}_chroma_data"

# ── Sanity ──────────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ docker not found in PATH" >&2
    exit 1
fi

# Refuse to run if the api/celery containers are up — those would crash
# (or worse, write garbage) mid-restore. Postgres must be UP because we
# pipe pg_restore through it; everything else must be DOWN.
RUNNING="$(docker ps --format '{{.Names}}' | grep "^${COMPOSE_PROJECT}-" || true)"
DANGER="$(echo "$RUNNING" | grep -E '^'"${COMPOSE_PROJECT}"'-(api|celery_worker|celery_beat|frontend)-1$' || true)"
if [ -n "$DANGER" ]; then
    echo "❌ The following containers are still running and must be stopped first:"
    echo "$DANGER" | sed 's/^/   - /'
    echo
    echo "   Run: docker compose stop api celery_worker celery_beat frontend"
    exit 1
fi

# Ensure postgres is up (we need it to accept the restore stream)
if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    echo "📦 Starting postgres container …"
    docker compose up -d postgres
    echo "   waiting for healthcheck …"
    for i in $(seq 1 30); do
        if docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done
fi

# ── Unpack the bundle ───────────────────────────────────────────────────────
STAGING="$(mktemp -d -t cloudsla-import-XXXXXX)"
trap 'rm -rf "$STAGING"' EXIT
echo "📦 Unpacking $BUNDLE → $STAGING"
tar -xzf "$BUNDLE" -C "$STAGING"

if [ ! -f "$STAGING/postgres.sql" ]; then
    echo "❌ bundle is missing postgres.sql — is this really an export-state tarball?" >&2
    exit 1
fi

# ── Show what we're about to do ─────────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════════════"
echo "  IMPORT PLAN"
echo "════════════════════════════════════════════════════════════════"
if [ -f "$STAGING/meta.txt" ]; then
    cat "$STAGING/meta.txt"
else
    echo "(no meta.txt — older export?)"
fi
echo "════════════════════════════════════════════════════════════════"
echo
echo "This will:"
echo "  - WIPE database '$PG_DB' and repopulate from postgres.sql"
echo "  - WIPE the '$CHROMA_VOLUME' Docker volume and restore from chromadb.tar.gz"
echo "  - Overwrite files in ./sla_docs/"
echo
read -p "Proceed? [y/N] " -n 1 -r REPLY
echo
if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# 1) Postgres restore
echo
echo "[1/3] Restoring Postgres …"
# --clean --if-exists in the dump handles dropping pre-existing tables,
# so we just need to pipe the SQL through psql. ON_ERROR_STOP catches
# any failure mid-restore.
docker exec -i "$PG_CONTAINER" psql \
    -U "$PG_USER" \
    -d "$PG_DB" \
    -v ON_ERROR_STOP=1 \
    --quiet \
    < "$STAGING/postgres.sql"
PROV_COUNT=$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "SELECT COUNT(*) FROM providers")
echo "      ✓ restored ($PROV_COUNT provider rows)"

# 2) ChromaDB restore
if [ -f "$STAGING/chromadb.tar.gz" ]; then
    echo "[2/3] Restoring ChromaDB volume ($CHROMA_VOLUME) …"

    # Make sure the volume exists; create it if not
    docker volume inspect "$CHROMA_VOLUME" >/dev/null 2>&1 || \
        docker volume create "$CHROMA_VOLUME" >/dev/null

    # Wipe + restore via a throwaway alpine container.
    # /data is the path Chroma 0.5.x uses internally; the volume's content
    # is identical regardless of where it ultimately gets mounted, but we
    # keep the path name consistent with export-state.sh.
    docker run --rm \
        -v "$CHROMA_VOLUME":/data \
        -v "$STAGING":/in:ro \
        alpine:3.19 \
        sh -c 'rm -rf /data/* /data/.[!.]* /data/..?* 2>/dev/null || true; cd /data && tar -xzf /in/chromadb.tar.gz'
    echo "      ✓ ChromaDB collection files restored"
else
    echo "[2/3] No chromadb.tar.gz in bundle — skipping"
fi

# 3) sla_docs/ restore
if [ -f "$STAGING/sla_docs.tar.gz" ]; then
    echo "[3/3] Restoring sla_docs/ …"
    # Wipe the existing directory then unpack — extract directly under
    # PROJECT_ROOT because the tar was made with `-C $PROJECT_ROOT sla_docs`.
    rm -rf "$PROJECT_ROOT/sla_docs"
    tar -xzf "$STAGING/sla_docs.tar.gz" -C "$PROJECT_ROOT"
    PDF_COUNT=$(find "$PROJECT_ROOT/sla_docs" -type f -name '*.pdf' 2>/dev/null | wc -l | tr -d ' ')
    echo "      ✓ restored ($PDF_COUNT PDFs)"
else
    echo "[3/3] No sla_docs.tar.gz in bundle — skipping"
fi

echo
echo "✅ Import complete."
echo
echo "Next:"
echo "   docker compose up -d"
echo "   open http://localhost:3000"
