"""
Seed the database with the 5 cloud providers and placeholder SLA metrics.

Run with:
    cd backend
    python -m scripts.seed_providers

This populates the providers table so /api/query works before real PDFs are ingested.
Replace placeholder metric values with real ones after ingesting actual SLA PDFs.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.models.models import Base, Provider, SLAMetrics

PROVIDERS = [
    {
        "name": "AWS",
        "website": "https://aws.amazon.com",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/9/93/Amazon_Web_Services_Logo.svg",
        "metrics": {
            "uptime_sla_pct": 99.99,
            "rto_hours": 4.0,
            "rpo_hours": 1.0,
            "support_response_min": 60,
            "penalty_credit_pct": 30,
            "regions": [
                "us-east-1", "us-west-2", "eu-west-1", "eu-central-1",
                "ap-southeast-1", "ap-northeast-1", "sa-east-1"
            ],
            "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS"],
            "source_clause": (
                "AWS EC2 SLA: AWS will use commercially reasonable efforts to make "
                "Amazon EC2 available with a Monthly Uptime Percentage of at least 99.99%."
            ),
        },
    },
    {
        "name": "Azure",
        "website": "https://azure.microsoft.com",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/a/a8/Microsoft_Azure_Logo.svg",
        "metrics": {
            "uptime_sla_pct": 99.995,
            "rto_hours": 1.0,
            "rpo_hours": 0.5,
            "support_response_min": 15,
            "penalty_credit_pct": 30,
            "regions": [
                "westeurope", "northeurope", "germanywestcentral", "germanynorth",
                "eastus", "westus2", "southeastasia", "australiaeast"
            ],
            "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS", "FedRAMP"],
            "source_clause": (
                "Azure SQL Business Critical: Microsoft guarantees that at least 99.995% "
                "of the time customers will have connectivity to their Azure SQL Business "
                "Critical database. RTO ≤ 30 seconds, RPO = 0 for zone-redundant deployment."
            ),
        },
    },
    {
        "name": "GCP",
        "website": "https://cloud.google.com",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/0/01/Google-cloud-platform.svg",
        "metrics": {
            "uptime_sla_pct": 99.95,
            "rto_hours": 2.0,
            "rpo_hours": 1.0,
            "support_response_min": 60,
            "penalty_credit_pct": 25,
            "regions": [
                "us-central1", "us-east1", "europe-west1", "europe-west3",
                "europe-west4", "asia-east1", "asia-southeast1"
            ],
            "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS"],
            "source_clause": (
                "Google Cloud SQL SLA: Google will use commercially reasonable efforts "
                "to make Cloud SQL available with a Monthly Uptime Percentage of at "
                "least 99.95% during any monthly billing period."
            ),
        },
    },
    {
        "name": "Oracle Cloud",
        "website": "https://www.oracle.com/cloud",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/5/50/Oracle_logo.svg",
        "metrics": {
            "uptime_sla_pct": 99.95,
            "rto_hours": 4.0,
            "rpo_hours": 2.0,
            "support_response_min": 60,
            "penalty_credit_pct": 25,
            "regions": [
                "us-ashburn-1", "us-phoenix-1", "eu-frankfurt-1",
                "eu-amsterdam-1", "ap-tokyo-1", "ap-sydney-1"
            ],
            "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "FedRAMP"],
            "source_clause": (
                "Oracle Cloud Infrastructure SLA: Oracle will provide a Monthly Uptime "
                "Percentage of at least 99.95% for Oracle Cloud Infrastructure Compute."
            ),
        },
    },
    {
        "name": "IBM Cloud",
        "website": "https://www.ibm.com/cloud",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/5/51/IBM_logo.svg",
        "metrics": {
            "uptime_sla_pct": 99.9,
            "rto_hours": 8.0,
            "rpo_hours": 4.0,
            "support_response_min": 120,
            "penalty_credit_pct": 10,
            "regions": [
                "us-south", "us-east", "eu-de", "eu-gb",
                "ap-north", "ap-south"
            ],
            "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "FedRAMP"],
            "source_clause": (
                "IBM Cloud SLA: IBM will make IBM Cloud services available with a "
                "monthly availability percentage of at least 99.9%."
            ),
        },
    },
]


async def seed():
    async_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(async_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for p_data in PROVIDERS:
            # Skip if already exists
            result = await session.execute(
                select(Provider).where(Provider.name == p_data["name"])
            )
            provider = result.scalar_one_or_none()

            if not provider:
                provider = Provider(
                    name=p_data["name"],
                    website=p_data["website"],
                    logo_url=p_data["logo_url"],
                )
                session.add(provider)
                await session.flush()
                print(f"  Created provider: {p_data['name']}")
            else:
                print(f"  Provider exists: {p_data['name']} — updating metrics")

            # Upsert placeholder SLA metrics
            metrics_result = await session.execute(
                select(SLAMetrics)
                .where(SLAMetrics.provider_id == provider.id)
                .limit(1)
            )
            existing_metrics = metrics_result.scalar_one_or_none()

            m = p_data["metrics"]
            if not existing_metrics:
                session.add(SLAMetrics(
                    provider_id=provider.id,
                    uptime_sla_pct=m["uptime_sla_pct"],
                    rto_hours=m["rto_hours"],
                    rpo_hours=m["rpo_hours"],
                    support_response_min=m["support_response_min"],
                    penalty_credit_pct=m["penalty_credit_pct"],
                    regions=m["regions"],
                    compliance=m["compliance"],
                    source_clause=m["source_clause"],
                ))

        await session.commit()
        print("\nSeeding complete.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
