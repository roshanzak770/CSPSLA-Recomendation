#!/usr/bin/env bash
#
# export-state.sh — bundle every piece of mutable state in this project
# into a single tarball that can be moved to another machine.
#
# What gets exported:
#   1. Postgres dump (providers, sla_metrics, sla_documents, sla_chunks,
#      rankings, feedback, alerts, etc.) via pg_dump --no-owner.
#   2. ChromaDB collection files from the chroma_data named volume.
#   3. The contents of ./sla_docs/ (raw ingested PDFs).
#   4. A meta.txt file describing what was captured and when.
#
# What is intentionally NOT exported:
#   - .env (secrets stay on the original machine — copy manually)
#   - Source code (use git for that)
#   - HuggingFace model cache (re-downloads in ~2 min on first query)
#   - Built frontend assets / Docker images (rebuild from source)
#
# Usage:
#   ./scripts/export-state.sh
#   ./scripts/export-state.sh /path/to/output.tar.gz   # custom output path
#
# The companion import-state.sh restores all of this on the target machine.
#
set -euo pipefail

# ── Resolve project root (parent of the scripts dir) ────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ── Configurable bits — read from .env if present, otherwise sane defaults ──
PG_USER="${POSTGRES_USER:-user}"
PG_DB="${POSTGRES_DB:-cloudsla}"
COMPOSE_PROJECT="cloudsla-recommender"   # docker compose project name prefix

# ── Output path ─────────────────────────────────────────────────────────────
TS="$(date +%Y%m%d-%H%M%S)"
OUTPUT="${1:-$PROJECT_ROOT/cloudsla-state-$TS.tar.gz}"

# ── Sanity checks ───────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ docker not found in PATH" >&2
    exit 1
fi

PG_CONTAINER="${COMPOSE_PROJECT}-postgres-1"
if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    echo "❌ Postgres container '$PG_CONTAINER' is not running." >&2
    echo "   Start the stack first: docker compose up -d postgres" >&2
    exit 1
fi

# ── Staging dir ─────────────────────────────────────────────────────────────
STAGING="$(mktemp -d -t cloudsla-export-XXXXXX)"
trap 'rm -rf "$STAGING"' EXIT

echo "📦 Exporting CloudSLA state → $OUTPUT"
echo "   Staging: $STAGING"
echo

# 1) Postgres dump
# --no-owner + --no-privileges so the dump restores cleanly into any DB
# regardless of the original role names.
echo "[1/4] Dumping Postgres ($PG_DB) …"
docker exec "$PG_CONTAINER" pg_dump \
    --username="$PG_USER" \
    --dbname="$PG_DB" \
    --no-owner \
    --no-privileges \
    --clean \
    --if-exists \
    > "$STAGING/postgres.sql"
PG_SIZE=$(wc -c < "$STAGING/postgres.sql" | tr -d ' ')
echo "      dumped $(($PG_SIZE / 1024)) KB"

# 2) ChromaDB — copy from the chroma_data named volume
# We start a throwaway alpine container with the volume mounted and tar
# its contents to stdout, which we capture into the staging dir.
# Mount the volume at /data because that's where ChromaDB persists in the
# 0.5.x image; the volume itself is just a directory we tar wholesale.
echo "[2/4] Snapshotting ChromaDB collection …"
CHROMA_VOLUME="${COMPOSE_PROJECT}_chroma_data"
if docker volume inspect "$CHROMA_VOLUME" >/dev/null 2>&1; then
    docker run --rm \
        -v "$CHROMA_VOLUME":/data:ro \
        -v "$STAGING":/out \
        alpine:3.19 \
        sh -c 'cd /data && tar -czf /out/chromadb.tar.gz . 2>/dev/null || true'
    CHROMA_SIZE=$(wc -c < "$STAGING/chromadb.tar.gz" 2>/dev/null | tr -d ' ' || echo 0)
    echo "      captured $(($CHROMA_SIZE / 1024)) KB"
else
    echo "      ⚠️  volume '$CHROMA_VOLUME' not found — skipping"
    echo "(no chromadb volume found at export time)" > "$STAGING/chromadb-missing.txt"
fi

# 3) Raw SLA PDFs
echo "[3/4] Copying sla_docs/ …"
if [ -d "$PROJECT_ROOT/sla_docs" ]; then
    tar -czf "$STAGING/sla_docs.tar.gz" -C "$PROJECT_ROOT" sla_docs
    SLA_SIZE=$(wc -c < "$STAGING/sla_docs.tar.gz" | tr -d ' ')
    echo "      captured $(($SLA_SIZE / 1024)) KB"
else
    echo "      ⚠️  sla_docs/ does not exist — skipping"
fi

# 4) Metadata file so the import script can sanity-check + the user can
#    see what's in the tarball without unpacking.
echo "[4/4] Writing meta.txt …"
cat > "$STAGING/meta.txt" <<EOF
CloudSLA-Recommender state export
==================================
Exported at:        $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Source hostname:    $(hostname)
Project root:       $PROJECT_ROOT
Postgres user/db:   $PG_USER / $PG_DB
Compose project:    $COMPOSE_PROJECT
Schema version:     $(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "SELECT MAX(version_num) FROM alembic_version" 2>/dev/null || echo "unknown")
Provider rows:      $(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "SELECT COUNT(*) FROM providers" 2>/dev/null || echo "?")
SLA documents:      $(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "SELECT COUNT(*) FROM sla_documents" 2>/dev/null || echo "?")
SLA chunks:         $(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "SELECT COUNT(*) FROM sla_chunks" 2>/dev/null || echo "?")
Pricing rows:       $(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "SELECT COUNT(*) FROM pricing_cache" 2>/dev/null || echo "?")

Files in this archive:
  postgres.sql    — pg_dump (--no-owner --clean --if-exists)
  chromadb.tar.gz — ChromaDB chroma_data volume contents
  sla_docs.tar.gz — raw SLA PDFs (./sla_docs/)
  meta.txt        — this file

Restore with: ./scripts/import-state.sh <this-file.tar.gz>
EOF

# ── Bundle ──────────────────────────────────────────────────────────────────
echo
echo "📦 Packing tarball …"
tar -czf "$OUTPUT" -C "$STAGING" .

FINAL_SIZE=$(wc -c < "$OUTPUT" | tr -d ' ')
echo
echo "✅ Done."
echo "   → $OUTPUT"
echo "   $(($FINAL_SIZE / 1024 / 1024)) MB"
echo
echo "Transfer this file to the target machine, then run:"
echo "   ./scripts/import-state.sh $(basename "$OUTPUT")"
