"""
GET /api/services/categories — returns the curated service catalog so the
frontend can populate dropdowns. Read-only, no admin auth required.
"""

from fastapi import APIRouter

from app.services.service_catalog import SERVICE_CATEGORIES, SERVICE_CATALOG

router = APIRouter()


@router.get("/services/categories")
async def list_service_categories():
    """
    Returns the full curated service catalog grouped by category.
    Shape:
      {
        "categories": ["compute", "storage", ...],
        "catalog": {
          "compute": {
            "AWS":   [{"name": "...", "uptime_sla_pct": ...}, ...],
            "Azure": [...],
            ...
          },
          ...
        }
      }
    """
    # Strip down to just the keys the frontend needs (name + uptime). The
    # full SLA values are recomputed server-side at query time; we don't
    # need to ship them all to the client.
    summary: dict[str, dict[str, list[dict]]] = {}
    for cat in SERVICE_CATEGORIES:
        summary[cat] = {}
        for provider, services in SERVICE_CATALOG.get(cat, {}).items():
            summary[cat][provider] = [
                {"name": s["name"], "uptime_sla_pct": s.get("uptime_sla_pct")}
                for s in services
            ]
    return {"categories": SERVICE_CATEGORIES, "catalog": summary}
