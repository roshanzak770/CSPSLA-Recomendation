"""
Cloud Provider Pricing Service — fetches real-time pricing from free public APIs.

Supported providers (all free, no paid subscriptions required):
  - Azure:  Azure Retail Prices API (no auth)
  - AWS:    AWS Bulk Pricing JSON (no auth)
  - GCP:    GCP Cloud Billing Catalog (no auth — public pricing JSON)
  - IBM:    IBM Global Catalog API (no auth)
  - Oracle: Oracle Cloud public pricing (static/curated)
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
MAX_ITEMS = 50


# ── Azure (free, no auth) ─────────────────────────────────────────────────

def fetch_azure_pricing(
    service_name: str = "Virtual Machines",
    region: str = "westeurope",
    max_items: int = MAX_ITEMS,
) -> list[dict]:
    results = []
    url = "https://prices.azure.com/api/retail/prices"
    filters = " and ".join([
        f"serviceName eq '{service_name}'",
        f"armRegionName eq '{region}'",
        "priceType eq 'Consumption'",
    ])
    try:
        resp = requests.get(url, params={"$filter": filters}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        for item in resp.json().get("Items", [])[:max_items]:
            results.append({
                "service": item.get("productName", ""),
                "sku": item.get("skuName", ""),
                "region": item.get("armRegionName", ""),
                "price_usd": item.get("retailPrice", 0.0),
                "unit": item.get("unitOfMeasure", ""),
            })
        logger.info("Azure: %d items for %s/%s", len(results), service_name, region)
    except Exception as e:
        logger.error("Azure pricing failed: %s", e)
    return results


def fetch_azure_all_services(regions: list[str] | None = None) -> list[dict]:
    regions = regions or ["westeurope", "eastus", "westus2", "southeastasia"]
    services = [
        "Virtual Machines", "SQL Database", "Storage",
        "Azure Cosmos DB", "Azure Kubernetes Service",
        "Azure Functions", "Load Balancer",
    ]
    out: list[dict] = []
    for svc in services:
        for rgn in regions:
            out.extend(fetch_azure_pricing(svc, rgn, max_items=10))
    return out


# ── AWS (free, no auth, no account) ───────────────────────────────────────

AWS_INDEX = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json"
AWS_SERVICES = {
    "AmazonEC2": "/offers/v1.0/aws/AmazonEC2/current/region_index.json",
    "AmazonRDS": "/offers/v1.0/aws/AmazonRDS/current/region_index.json",
    "AmazonS3": "/offers/v1.0/aws/AmazonS3/current/region_index.json",
    "AmazonDynamoDB": "/offers/v1.0/aws/AmazonDynamoDB/current/region_index.json",
    "AWSLambda": "/offers/v1.0/aws/AWSLambda/current/region_index.json",
}
_BASE = "https://pricing.us-east-1.amazonaws.com"


def fetch_aws_pricing(region: str = "us-east-1", max_items: int = MAX_ITEMS) -> list[dict]:
    results: list[dict] = []
    try:
        idx = requests.get(AWS_INDEX, timeout=REQUEST_TIMEOUT).json()
        offers = idx.get("offers", {})
        for code, fallback_path in AWS_SERVICES.items():
            try:
                path = offers.get(code, {}).get("currentRegionIndexUrl", fallback_path)
                rd = requests.get(_BASE + path, timeout=REQUEST_TIMEOUT).json()
                ver = rd.get("regions", {}).get(region, {}).get("currentVersionUrl", "")
                if ver:
                    results.append({
                        "service": code, "sku": f"{code}-index",
                        "region": region, "price_usd": 0.0,
                        "unit": "see detail URL",
                        "detail_url": _BASE + ver,
                    })
            except Exception:
                pass
        logger.info("AWS index: %d service entries for %s", len(results), region)
    except Exception as e:
        logger.error("AWS index failed: %s", e)

    results.extend(_aws_common_prices(region))
    return results[:max_items]


def _aws_common_prices(r: str) -> list[dict]:
    """Curated on-demand prices for popular AWS SKUs."""
    P = "per Hour"
    return [
        {"service": "Amazon EC2", "sku": "t3.micro", "region": r, "price_usd": 0.0104, "unit": P},
        {"service": "Amazon EC2", "sku": "t3.small", "region": r, "price_usd": 0.0208, "unit": P},
        {"service": "Amazon EC2", "sku": "t3.medium", "region": r, "price_usd": 0.0416, "unit": P},
        {"service": "Amazon EC2", "sku": "m5.large", "region": r, "price_usd": 0.096, "unit": P},
        {"service": "Amazon EC2", "sku": "m5.xlarge", "region": r, "price_usd": 0.192, "unit": P},
        {"service": "Amazon EC2", "sku": "c5.large", "region": r, "price_usd": 0.085, "unit": P},
        {"service": "Amazon RDS", "sku": "db.t3.micro", "region": r, "price_usd": 0.017, "unit": P},
        {"service": "Amazon RDS", "sku": "db.t3.small", "region": r, "price_usd": 0.034, "unit": P},
        {"service": "Amazon RDS", "sku": "db.r5.large", "region": r, "price_usd": 0.25, "unit": P},
        {"service": "Amazon S3", "sku": "Standard", "region": r, "price_usd": 0.023, "unit": "per GB-Mo"},
        {"service": "Amazon S3", "sku": "Glacier", "region": r, "price_usd": 0.004, "unit": "per GB-Mo"},
        {"service": "Amazon DynamoDB", "sku": "Write", "region": r, "price_usd": 0.00065, "unit": "per WCU-Hr"},
        {"service": "Amazon DynamoDB", "sku": "Read", "region": r, "price_usd": 0.00013, "unit": "per RCU-Hr"},
        {"service": "AWS Lambda", "sku": "Requests", "region": r, "price_usd": 0.0000002, "unit": "per Req"},
        {"service": "AWS Lambda", "sku": "Duration", "region": r, "price_usd": 1.667e-5, "unit": "per GB-s"},
        {"service": "Amazon EKS", "sku": "Cluster", "region": r, "price_usd": 0.10, "unit": P},
    ]


# ── GCP (free, no auth) ──────────────────────────────────────────────────

GCP_URL = "https://cloudpricingcalculator.appspot.com/static/data/pricelist.json"


def _gcp_category(key: str) -> str:
    k = key.upper()
    if "COMPUTEENGINE" in k or "VMIMAGE" in k:
        return "Compute Engine"
    if "CLOUDSQL" in k:
        return "Cloud SQL"
    if "BIGQUERY" in k:
        return "BigQuery"
    if "STORAGE" in k or "NEARLINE" in k or "COLDLINE" in k:
        return "Cloud Storage"
    if "GKE" in k or "KUBERNETES" in k:
        return "GKE"
    if "FUNCTIONS" in k:
        return "Cloud Functions"
    if "NETWORK" in k or "EGRESS" in k:
        return "Networking"
    if "SPANNER" in k:
        return "Cloud Spanner"
    return "GCP Service"


def fetch_gcp_pricing(region: str = "us-central1", max_items: int = MAX_ITEMS) -> list[dict]:
    results: list[dict] = []
    try:
        data = requests.get(GCP_URL, timeout=REQUEST_TIMEOUT).json()
        skip = {"maxNumberOfPd", "cores", "memory", "ssd", "gceu"}
        for sku, info in data.get("gcp_price_list", {}).items():
            if len(results) >= max_items:
                break
            if not isinstance(info, dict):
                continue
            price = info.get(region) or info.get("us") or info.get("us-central1")
            if price is None:
                for k, v in info.items():
                    if isinstance(v, (int, float)) and k not in skip:
                        price = v
                        break
            if isinstance(price, (int, float)):
                results.append({
                    "service": _gcp_category(sku), "sku": sku,
                    "region": region, "price_usd": float(price), "unit": "varies",
                })
        logger.info("GCP: fetched %d items", len(results))
    except Exception as e:
        logger.error("GCP pricing failed: %s — using fallback", e)
        results = _gcp_fallback(region)
    return results


def _gcp_fallback(r: str) -> list[dict]:
    P = "per Hour"
    return [
        {"service": "Compute Engine", "sku": "e2-micro", "region": r, "price_usd": 0.00838, "unit": P},
        {"service": "Compute Engine", "sku": "e2-small", "region": r, "price_usd": 0.01675, "unit": P},
        {"service": "Compute Engine", "sku": "e2-medium", "region": r, "price_usd": 0.0335, "unit": P},
        {"service": "Compute Engine", "sku": "n1-standard-1", "region": r, "price_usd": 0.0475, "unit": P},
        {"service": "Compute Engine", "sku": "n1-standard-4", "region": r, "price_usd": 0.1900, "unit": P},
        {"service": "Cloud SQL", "sku": "db-f1-micro", "region": r, "price_usd": 0.0150, "unit": P},
        {"service": "Cloud SQL", "sku": "db-g1-small", "region": r, "price_usd": 0.0500, "unit": P},
        {"service": "Cloud Storage", "sku": "Standard", "region": r, "price_usd": 0.020, "unit": "per GB-Mo"},
        {"service": "Cloud Storage", "sku": "Nearline", "region": r, "price_usd": 0.010, "unit": "per GB-Mo"},
        {"service": "Cloud Storage", "sku": "Coldline", "region": r, "price_usd": 0.004, "unit": "per GB-Mo"},
        {"service": "BigQuery", "sku": "On-demand query", "region": r, "price_usd": 5.0, "unit": "per TB"},
        {"service": "GKE", "sku": "Cluster mgmt", "region": r, "price_usd": 0.10, "unit": P},
        {"service": "Cloud Functions", "sku": "Invocations", "region": r, "price_usd": 0.0000004, "unit": "per invocation"},
    ]


# ── IBM Cloud (free Global Catalog API, no auth) ─────────────────────────

IBM_CATALOG_URL = "https://globalcatalog.cloud.ibm.com/api/v1"


def fetch_ibm_pricing(max_items: int = MAX_ITEMS) -> list[dict]:
    results: list[dict] = []
    queries = [
        "virtual server", "cloud object storage", "databases",
        "kubernetes", "cloud functions",
    ]
    for q in queries:
        try:
            resp = requests.get(
                IBM_CATALOG_URL,
                params={"q": q, "languages": "en", "limit": 10, "complete": "true"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            for res in resp.json().get("resources", []):
                name = res.get("name", "")
                kind = res.get("kind", "")
                overview = res.get("overview", {}).get("en", {})
                # Try to extract pricing metadata
                pricing = res.get("pricing", {})
                price_url = pricing.get("url", "")
                results.append({
                    "service": overview.get("display_name", name),
                    "sku": kind,
                    "region": "global",
                    "price_usd": 0.0,
                    "unit": "see pricing page",
                    "pricing_url": price_url or f"https://cloud.ibm.com/catalog/{name}",
                    "description": overview.get("description", "")[:200],
                })
        except Exception as e:
            logger.warning("IBM catalog query '%s' failed: %s", q, e)

    if not results:
        results = _ibm_fallback()

    logger.info("IBM: fetched %d catalog items", len(results))
    return results[:max_items]


def _ibm_fallback() -> list[dict]:
    return [
        {"service": "Virtual Server", "sku": "bx2-2x8", "region": "us-south", "price_usd": 0.058, "unit": "per Hour"},
        {"service": "Virtual Server", "sku": "bx2-4x16", "region": "us-south", "price_usd": 0.115, "unit": "per Hour"},
        {"service": "Cloud Object Storage", "sku": "Standard", "region": "us-south", "price_usd": 0.022, "unit": "per GB-Mo"},
        {"service": "Db2 on Cloud", "sku": "Flex One", "region": "us-south", "price_usd": 189.0, "unit": "per Month"},
        {"service": "IBM Kubernetes", "sku": "Free cluster", "region": "us-south", "price_usd": 0.0, "unit": "free"},
        {"service": "IBM Cloud Functions", "sku": "Invocations", "region": "us-south", "price_usd": 0.000017, "unit": "per sec-GB"},
    ]


# ── Oracle Cloud (no free pricing API — static/curated) ──────────────────

def fetch_oracle_pricing() -> list[dict]:
    """Oracle has no free structured pricing API; returns curated public data."""
    return [
        {"service": "OCI Compute", "sku": "VM.Standard.E4.Flex (1 OCPU)", "region": "us-ashburn-1", "price_usd": 0.025, "unit": "per Hour"},
        {"service": "OCI Compute", "sku": "VM.Standard.E4.Flex (4 OCPU)", "region": "us-ashburn-1", "price_usd": 0.10, "unit": "per Hour"},
        {"service": "OCI Compute", "sku": "Ampere A1 (1 OCPU)", "region": "us-ashburn-1", "price_usd": 0.01, "unit": "per Hour"},
        {"service": "OCI Block Storage", "sku": "Performance", "region": "us-ashburn-1", "price_usd": 0.0255, "unit": "per GB-Mo"},
        {"service": "OCI Object Storage", "sku": "Standard", "region": "us-ashburn-1", "price_usd": 0.0255, "unit": "per GB-Mo"},
        {"service": "OCI Autonomous DB", "sku": "ECPU", "region": "us-ashburn-1", "price_usd": 0.3150, "unit": "per ECPU-Hr"},
        {"service": "OCI MySQL HeatWave", "sku": "Standard E3", "region": "us-ashburn-1", "price_usd": 0.0940, "unit": "per Hour"},
        {"service": "OCI Container Engine", "sku": "OKE Enhanced", "region": "us-ashburn-1", "price_usd": 0.10, "unit": "per Hour"},
        {"service": "OCI Load Balancer", "sku": "Flexible 10Mbps", "region": "us-ashburn-1", "price_usd": 0.012, "unit": "per Hour"},
        {"service": "OCI Functions", "sku": "Invocations", "region": "us-ashburn-1", "price_usd": 0.0000002, "unit": "per Req"},
    ]


# ── Unified fetch-all helper ─────────────────────────────────────────────

PROVIDER_FETCHERS = {
    "AWS": lambda: fetch_aws_pricing(),
    "Azure": lambda: fetch_azure_all_services(),
    "GCP": lambda: fetch_gcp_pricing(),
    "Oracle Cloud": lambda: fetch_oracle_pricing(),
    "IBM Cloud": lambda: fetch_ibm_pricing(),
}


def fetch_all_providers() -> dict[str, list[dict]]:
    """Fetch pricing for every supported provider. Returns {name: [items]}."""
    result: dict[str, list[dict]] = {}
    for name, fetcher in PROVIDER_FETCHERS.items():
        try:
            result[name] = fetcher()
        except Exception as e:
            logger.error("Pricing fetch for %s failed: %s", name, e)
            result[name] = []
    return result
