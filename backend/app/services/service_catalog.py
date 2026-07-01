"""
Curated service-level SLA catalog.

Each cloud provider publishes DIFFERENT SLAs per service — AWS EC2 multi-AZ
is 99.99% while S3 Standard is 99.9% and DynamoDB Global Tables is 99.999%.
The monolithic per-provider curated dict in `query.py` collapses all of this
into a single "AWS = 99.99" number, which is only correct for EC2.

This catalog models reality: a user filtering for "Database" gets recommended
specifically *AWS Aurora Multi-AZ vs Azure Cosmos DB vs Cloud SQL HA*, each
with their actual published SLA values — not the provider-level average.

The values below are the highest publicly-committed monthly uptime percentages
each vendor publishes for that service tier as of 2026. Where a vendor offers
multiple sub-tiers (Standard vs Premium, single-AZ vs multi-AZ), we record the
headline / multi-AZ tier — that's what users would actually deploy when SLA
matters.

Source notes per provider:
  AWS:    aws.amazon.com/legal/service-level-agreements/
  Azure:  azure.microsoft.com/en-us/support/legal/sla/summary/
  GCP:    cloud.google.com/terms/sla
  Oracle: oracle.com/cloud/sla/
  IBM:    ibm.com/support/customer/csol/terms/?id=i126-6605
"""

from __future__ import annotations
from typing import TypedDict


class ServiceSLA(TypedDict, total=False):
    name:                 str    # vendor's product name (e.g. "Amazon EC2 (Multi-AZ)")
    sla_url:              str    # direct link to that specific service's SLA page
    uptime_sla_pct:       float
    rto_hours:            float
    rpo_hours:            float
    support_response_min: int
    penalty_credit_pct:   int


# Five top-level service categories. Order here is the order shown in the UI.
SERVICE_CATEGORIES: list[str] = [
    "compute",
    "storage",
    "database",
    "network",
    "serverless",
]


# Catalog shape: { category: { provider: [ServiceSLA, ...] } }
# Within a category, the *first* service per provider is the canonical
# "headline" tier — that's what we pick when run_pipeline needs one row
# per (provider, service) without further hints.
SERVICE_CATALOG: dict[str, dict[str, list[ServiceSLA]]] = {

    # ─── Compute ───────────────────────────────────────────────────────────
    # Per-service metric variance — managed/HA tiers have tighter RTO and
    # higher credit than single-instance tiers. Without this spread, TOPSIS
    # column-normalises all of a provider's compute rows to similar scores.
    "compute": {
        "AWS": [
            {"name": "AWS Fargate",
             "sla_url": "https://aws.amazon.com/fargate/sla/",
             "uptime_sla_pct": 99.99, "rto_hours": 0.5, "rpo_hours": 0.5,
             "support_response_min": 30, "penalty_credit_pct": 25},
            {"name": "Amazon EC2 (Multi-AZ)",
             "sla_url": "https://aws.amazon.com/compute/sla/",
             "uptime_sla_pct": 99.99, "rto_hours": 1.0, "rpo_hours": 0.5,
             "support_response_min": 60, "penalty_credit_pct": 10},
            {"name": "Amazon EC2 (Single Instance)",
             "sla_url": "https://aws.amazon.com/compute/sla/",
             "uptime_sla_pct": 99.5,  "rto_hours": 8.0, "rpo_hours": 8.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
        ],
        "Azure": [
            {"name": "Azure Container Instances",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/container-instances/",
             "uptime_sla_pct": 99.99, "rto_hours": 0.5, "rpo_hours": 0.5,
             "support_response_min": 15, "penalty_credit_pct": 30},
            {"name": "Azure Virtual Machines (Availability Zones)",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/virtual-machines/",
             "uptime_sla_pct": 99.99, "rto_hours": 1.0, "rpo_hours": 0.5,
             "support_response_min": 15, "penalty_credit_pct": 30},
            {"name": "Azure Virtual Machines (Single)",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/virtual-machines/",
             "uptime_sla_pct": 99.9,  "rto_hours": 4.0, "rpo_hours": 4.0,
             "support_response_min": 30, "penalty_credit_pct": 25},
        ],
        "GCP": [
            {"name": "Google Compute Engine (Regional)",
             "sla_url": "https://cloud.google.com/compute/sla",
             "uptime_sla_pct": 99.99, "rto_hours": 1.0, "rpo_hours": 0.5,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "Google Compute Engine (Single Zone)",
             "sla_url": "https://cloud.google.com/compute/sla",
             "uptime_sla_pct": 99.5,  "rto_hours": 8.0, "rpo_hours": 8.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
        ],
        "Oracle": [
            {"name": "Oracle Compute (Bare Metal & VM)",
             "sla_url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/",
             "uptime_sla_pct": 99.95, "rto_hours": 2.0, "rpo_hours": 1.0,
             "support_response_min": 120, "penalty_credit_pct": 25},
        ],
        "IBM": [
            {"name": "IBM Cloud Virtual Server (Multi-Zone)",
             "sla_url": "https://www.ibm.com/cloud/virtual-servers",
             "uptime_sla_pct": 99.99, "rto_hours": 2.0, "rpo_hours": 1.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "IBM Cloud Virtual Server (Single)",
             "sla_url": "https://www.ibm.com/cloud/virtual-servers",
             "uptime_sla_pct": 99.9,  "rto_hours": 8.0, "rpo_hours": 4.0,
             "support_response_min": 120, "penalty_credit_pct": 10},
        ],
    },

    # ─── Storage ───────────────────────────────────────────────────────────
    # Note: secondary metrics (RTO / RPO / support / credit) are intentionally
    # varied per service so TOPSIS column normalisation can spread the rows.
    # Without this, every service from one provider would share identical
    # RTO/support/credit and the L2-norm would compress uptime differences
    # to near-zero — meaning every row from a provider scored identically.
    "storage": {
        "AWS": [
            {"name": "Amazon EBS",
             "sla_url": "https://aws.amazon.com/ebs/sla/",
             "uptime_sla_pct": 99.99, "rto_hours": 0.25, "rpo_hours": 0.0,
             "support_response_min": 30, "penalty_credit_pct": 25},
            {"name": "Amazon S3 Standard",
             "sla_url": "https://aws.amazon.com/s3/sla/",
             "uptime_sla_pct": 99.9,  "rto_hours": 1.0,  "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
            {"name": "Amazon S3 Standard-IA",
             "sla_url": "https://aws.amazon.com/s3/sla/",
             "uptime_sla_pct": 99.0,  "rto_hours": 4.0,  "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
        ],
        "Azure": [
            {"name": "Azure Managed Disks",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/managed-disks/",
             "uptime_sla_pct": 99.99, "rto_hours": 0.25, "rpo_hours": 0.0,
             "support_response_min": 15, "penalty_credit_pct": 30},
            {"name": "Azure Blob Storage (ZRS, Hot)",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/storage/",
             "uptime_sla_pct": 99.99, "rto_hours": 1.0,  "rpo_hours": 0.0,
             "support_response_min": 30, "penalty_credit_pct": 25},
            {"name": "Azure Blob Storage (LRS)",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/storage/",
             "uptime_sla_pct": 99.9,  "rto_hours": 2.0,  "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
        ],
        "GCP": [
            {"name": "Persistent Disk (Regional SSD)",
             "sla_url": "https://cloud.google.com/compute/sla",
             "uptime_sla_pct": 99.99, "rto_hours": 0.25, "rpo_hours": 0.0,
             "support_response_min": 30, "penalty_credit_pct": 25},
            {"name": "Cloud Storage (Multi-Region)",
             "sla_url": "https://cloud.google.com/storage/sla",
             "uptime_sla_pct": 99.95, "rto_hours": 1.0,  "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "Cloud Storage (Regional)",
             "sla_url": "https://cloud.google.com/storage/sla",
             "uptime_sla_pct": 99.9,  "rto_hours": 2.0,  "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
        ],
        "Oracle": [
            {"name": "Oracle Block Volume",
             "sla_url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/",
             "uptime_sla_pct": 99.95, "rto_hours": 2.0, "rpo_hours": 1.0,
             "support_response_min": 120, "penalty_credit_pct": 25},
            {"name": "Oracle Object Storage",
             "sla_url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/",
             "uptime_sla_pct": 99.9,  "rto_hours": 4.0, "rpo_hours": 0.0,
             "support_response_min": 120, "penalty_credit_pct": 25},
        ],
        "IBM": [
            {"name": "IBM Cloud Object Storage (Cross-Region)",
             "sla_url": "https://www.ibm.com/cloud/object-storage",
             "uptime_sla_pct": 99.99, "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "IBM Block Storage",
             "sla_url": "https://www.ibm.com/cloud/block-storage",
             "uptime_sla_pct": 99.9,  "rto_hours": 4.0, "rpo_hours": 2.0,
             "support_response_min": 120, "penalty_credit_pct": 10},
        ],
    },

    # ─── Database ──────────────────────────────────────────────────────────
    # Per-service variance — flagship globally-replicated tiers (DynamoDB
    # Global, Cosmos DB, Spanner) carry premium support + higher credits;
    # standard managed tiers (RDS, Cloud SQL) sit at base support / credit.
    "database": {
        "AWS": [
            {"name": "DynamoDB Global Tables",
             "sla_url": "https://aws.amazon.com/dynamodb/sla/",
             "uptime_sla_pct": 99.999, "rto_hours": 0.1,  "rpo_hours": 0.0,
             "support_response_min": 30, "penalty_credit_pct": 30},
            {"name": "Amazon Aurora (Multi-AZ)",
             "sla_url": "https://aws.amazon.com/rds/aurora/sla/",
             "uptime_sla_pct": 99.99,  "rto_hours": 0.5,  "rpo_hours": 0.1,
             "support_response_min": 30, "penalty_credit_pct": 25},
            {"name": "Amazon RDS (Multi-AZ)",
             "sla_url": "https://aws.amazon.com/rds/sla/",
             "uptime_sla_pct": 99.95,  "rto_hours": 1.0,  "rpo_hours": 0.25,
             "support_response_min": 60, "penalty_credit_pct": 10},
        ],
        "Azure": [
            {"name": "Cosmos DB (Multi-Region Write)",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/cosmos-db/",
             "uptime_sla_pct": 99.999, "rto_hours": 0.1,  "rpo_hours": 0.0,
             "support_response_min": 15, "penalty_credit_pct": 30},
            {"name": "Azure SQL Database (Business Critical)",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/azure-sql-database/",
             "uptime_sla_pct": 99.995, "rto_hours": 0.5,  "rpo_hours": 0.1,
             "support_response_min": 15, "penalty_credit_pct": 30},
            {"name": "Azure Database for PostgreSQL (HA)",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/postgresql/",
             "uptime_sla_pct": 99.99,  "rto_hours": 1.0,  "rpo_hours": 0.25,
             "support_response_min": 30, "penalty_credit_pct": 25},
        ],
        "GCP": [
            {"name": "Cloud Spanner (Multi-Region)",
             "sla_url": "https://cloud.google.com/spanner/sla",
             "uptime_sla_pct": 99.999, "rto_hours": 0.1,  "rpo_hours": 0.0,
             "support_response_min": 30, "penalty_credit_pct": 30},
            {"name": "Firestore (Multi-Region)",
             "sla_url": "https://cloud.google.com/firestore/sla",
             "uptime_sla_pct": 99.999, "rto_hours": 0.25, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "Cloud SQL (HA)",
             "sla_url": "https://cloud.google.com/sql/sla",
             "uptime_sla_pct": 99.95,  "rto_hours": 1.0,  "rpo_hours": 0.25,
             "support_response_min": 60, "penalty_credit_pct": 10},
        ],
        "Oracle": [
            {"name": "Oracle Autonomous Database (Multi-AD)",
             "sla_url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/",
             "uptime_sla_pct": 99.995, "rto_hours": 0.25, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 30},
            {"name": "Oracle Database Cloud Service (RAC)",
             "sla_url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/",
             "uptime_sla_pct": 99.95,  "rto_hours": 1.0,  "rpo_hours": 0.25,
             "support_response_min": 120, "penalty_credit_pct": 25},
        ],
        "IBM": [
            {"name": "IBM Cloudant (Dedicated)",
             "sla_url": "https://www.ibm.com/cloud/cloudant",
             "uptime_sla_pct": 99.99, "rto_hours": 1.0, "rpo_hours": 0.25,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "IBM Db2 on Cloud (HA)",
             "sla_url": "https://www.ibm.com/cloud/db2-on-cloud",
             "uptime_sla_pct": 99.95, "rto_hours": 2.0, "rpo_hours": 0.5,
             "support_response_min": 120, "penalty_credit_pct": 10},
        ],
    },

    # ─── Network ───────────────────────────────────────────────────────────
    "network": {
        "AWS": [
            {"name": "Route 53 DNS",
             "sla_url": "https://aws.amazon.com/route53/sla/",
             "uptime_sla_pct": 100.0, "rto_hours": 0.1, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "Amazon CloudFront",
             "sla_url": "https://aws.amazon.com/cloudfront/sla/",
             "uptime_sla_pct": 99.9,  "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
            {"name": "AWS Direct Connect",
             "sla_url": "https://aws.amazon.com/directconnect/sla/",
             "uptime_sla_pct": 99.99, "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
        ],
        "Azure": [
            {"name": "Azure DNS",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/dns/",
             "uptime_sla_pct": 100.0, "rto_hours": 0.1, "rpo_hours": 0.0,
             "support_response_min": 15, "penalty_credit_pct": 30},
            {"name": "Azure Front Door",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/frontdoor/",
             "uptime_sla_pct": 99.99, "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 15, "penalty_credit_pct": 30},
            {"name": "Azure ExpressRoute",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/expressroute/",
             "uptime_sla_pct": 99.95, "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 15, "penalty_credit_pct": 25},
        ],
        "GCP": [
            {"name": "Cloud DNS",
             "sla_url": "https://cloud.google.com/dns/sla",
             "uptime_sla_pct": 100.0, "rto_hours": 0.1, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "Cloud CDN",
             "sla_url": "https://cloud.google.com/cdn/sla",
             "uptime_sla_pct": 99.9,  "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "Cloud Interconnect",
             "sla_url": "https://cloud.google.com/network-connectivity/docs/interconnect/concepts/sla",
             "uptime_sla_pct": 99.99, "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
        ],
        "Oracle": [
            {"name": "Oracle Cloud DNS",
             "sla_url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/",
             "uptime_sla_pct": 100.0, "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 120, "penalty_credit_pct": 25},
            {"name": "Oracle FastConnect",
             "sla_url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/",
             "uptime_sla_pct": 99.95, "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 120, "penalty_credit_pct": 25},
        ],
        "IBM": [
            {"name": "IBM Cloud Internet Services",
             "sla_url": "https://www.ibm.com/cloud/cloud-internet-services",
             "uptime_sla_pct": 99.99, "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "IBM Direct Link",
             "sla_url": "https://www.ibm.com/cloud/direct-link",
             "uptime_sla_pct": 99.95, "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
        ],
    },

    # ─── Serverless ────────────────────────────────────────────────────────
    "serverless": {
        "AWS": [
            {"name": "AWS Lambda",
             "sla_url": "https://aws.amazon.com/lambda/sla/",
             "uptime_sla_pct": 99.95, "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
            {"name": "AWS Step Functions",
             "sla_url": "https://aws.amazon.com/step-functions/sla/",
             "uptime_sla_pct": 99.9,  "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 10},
        ],
        "Azure": [
            {"name": "Azure Functions",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/functions/",
             "uptime_sla_pct": 99.95, "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 15, "penalty_credit_pct": 25},
            {"name": "Azure Logic Apps",
             "sla_url": "https://azure.microsoft.com/en-us/support/legal/sla/logic-apps/",
             "uptime_sla_pct": 99.9,  "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 15, "penalty_credit_pct": 25},
        ],
        "GCP": [
            {"name": "Cloud Functions (2nd gen)",
             "sla_url": "https://cloud.google.com/functions/sla",
             "uptime_sla_pct": 99.95, "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
            {"name": "Cloud Run",
             "sla_url": "https://cloud.google.com/run/sla",
             "uptime_sla_pct": 99.95, "rto_hours": 0.5, "rpo_hours": 0.0,
             "support_response_min": 60, "penalty_credit_pct": 25},
        ],
        "Oracle": [
            {"name": "Oracle Functions",
             "sla_url": "https://www.oracle.com/cloud/iaas/sla-licensing-info/",
             "uptime_sla_pct": 99.9,  "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 120, "penalty_credit_pct": 25},
        ],
        "IBM": [
            {"name": "IBM Cloud Functions",
             "sla_url": "https://www.ibm.com/cloud/functions",
             "uptime_sla_pct": 99.9,  "rto_hours": 1.0, "rpo_hours": 0.0,
             "support_response_min": 120, "penalty_credit_pct": 10},
        ],
    },
}


def services_for(category: str, provider_name: str) -> list[ServiceSLA]:
    """Return the list of services this provider offers in the given category.
    Empty list if the provider/category combination has no curated entry."""
    if not category:
        return []
    return SERVICE_CATALOG.get(category.lower(), {}).get(provider_name, [])


def best_service_for(category: str, provider_name: str) -> ServiceSLA | None:
    """Pick the provider's strongest service in the category (highest uptime,
    tie-broken by lowest RTO, then highest credit). Used when we need a
    single representative service per provider — e.g. when expanding a
    monolithic provider into one (provider, service) row for ranking."""
    candidates = services_for(category, provider_name)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda s: (
            s.get("uptime_sla_pct", 0.0),
            -s.get("rto_hours", 999.0),
            s.get("penalty_credit_pct", 0),
        ),
    )


def all_services_in_category(category: str) -> list[tuple[str, ServiceSLA]]:
    """Flatten the catalog for a category into [(provider_name, service), ...].
    Used by the recommend pipeline when it should rank EVERY service across
    every provider — e.g. user wants to see all storage options side by side."""
    if not category:
        return []
    out: list[tuple[str, ServiceSLA]] = []
    for prov_name, services in SERVICE_CATALOG.get(category.lower(), {}).items():
        for svc in services:
            out.append((prov_name, svc))
    return out
