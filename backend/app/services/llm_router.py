"""
LLM Router — wraps HuggingFace Inference API for:
  - SLA metrics extraction  (Llama-3.1-8B-Instruct)
  - Query understanding     (Qwen2.5-7B-Instruct)
  - Ranking explanation     (Qwen2.5-7B-Instruct)
"""

import json
import re

from huggingface_hub import InferenceClient

from app.core.config import settings


class LLMRouter:
    def __init__(self):
        self.extractor = InferenceClient(
            model="HuggingFaceH4/zephyr-7b-beta",
            token=settings.hf_token,
        )
        self.reasoner = InferenceClient(
            model="HuggingFaceH4/zephyr-7b-beta",
            token=settings.hf_token,
        )

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM output, stripping markdown fences if present."""
        text = text.strip()
        # Remove ```json ... ``` or ``` ... ``` fences
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1)
        return json.loads(text)

    def extract_sla_metrics(self, sla_text: str) -> dict:
        """
        Given raw SLA text, extract structured metrics.
        Returns a dict with keys: uptime_sla_pct, rto_hours, rpo_hours,
        support_response_min, penalty_credit_pct, regions, compliance, source_clause.
        """
        prompt = f"""Extract SLA metrics from this text. Return ONLY valid JSON with these exact keys:
{{
  "uptime_sla_pct": float or null,
  "rto_hours": float or null,
  "rpo_hours": float or null,
  "support_response_min": int or null,
  "penalty_credit_pct": int or null,
  "regions": ["string"],
  "compliance": ["string"],
  "source_clause": "exact quote from text"
}}
Text:
{sla_text}"""

        response = self.extractor.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0,
        )
        raw = response.choices[0].message.content
        return self._parse_json(raw)

    def understand_query(self, query: str) -> dict:
        """
        Parse a natural language user query into structured requirements.
        Returns dict with uptime_required_pct, rto_hours, rpo_hours, region,
        country, compliance, category, sensitivity, budget_usd_monthly.
        """
        prompt = f"""Extract cloud service requirements from this user query. Return ONLY valid JSON:
{{
  "uptime_required_pct": float or null,
  "rto_hours": float or null,
  "rpo_hours": float or null,
  "region": "string or null",
  "country": "string or null",
  "compliance": ["string"],
  "category": "database|compute|storage|network|null",
  "sensitivity": "LOW|MEDIUM|HIGH",
  "budget_usd_monthly": float or null
}}
Query: {query}"""

        response = self.reasoner.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0,
        )
        raw = response.choices[0].message.content
        return self._parse_json(raw)

    def generate_explanation(self, query: str, providers: list, lang: str = "English") -> str:
        """
        Generate a human-readable ranking explanation for the top providers.
        Returns plain text response in the specified language.
        """
        provider_summary = json.dumps(providers, indent=2)
        prompt = f"""User requirement: {query}

Ranked cloud providers with SLA data:
{provider_summary}

Write a concise explanation of the ranking, citing specific SLA clauses.
Mention why each provider ranked where it did relative to the user's requirements.
Respond in {lang}."""

        response = self.reasoner.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
        )
        return response.choices[0].message.content

    def describe_sla_change(self, old_chunk: str, new_chunk: str) -> dict:
        """
        Given two SLA text chunks, describe what changed and classify severity.
        Returns: {"description": str, "severity": "LOW|MEDIUM|HIGH|CRITICAL|POSITIVE"}
        """
        prompt = f"""Compare these two SLA document excerpts and identify what changed.
Return ONLY valid JSON:
{{
  "description": "one sentence describing the change",
  "change_type": "UPTIME_REDUCED|UPTIME_IMPROVED|RTO_INCREASED|RTO_REDUCED|PENALTY_REDUCED|PENALTY_INCREASED|REGION_REMOVED|COMPLIANCE_REMOVED|WORDING_CHANGE|OTHER",
  "severity": "LOW|MEDIUM|HIGH|CRITICAL|POSITIVE"
}}

Old text:
{old_chunk}

New text:
{new_chunk}"""

        response = self.reasoner.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0,
        )
        raw = response.choices[0].message.content
        return self._parse_json(raw)


llm_router = LLMRouter()
