"""
LLM Router — Groq API (llama-3.1-8b-instant).

Free tier: 14,400 requests/day, 30 req/min.
Fallback: llama-3.2-3b-preview if primary is rate-limited.
"""

import json
import re
import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL      = "https://api.groq.com/openai/v1/chat/completions"
_PRIMARY_MODEL = "llama-3.1-8b-instant"
_FALLBACK_MODEL = "llama-3.2-3b-preview"
_TIMEOUT = 30


def _chat(messages: list, max_tokens: int = 500, temperature: float = 0.1) -> str:
    """Call Groq chat completions. Tries primary then fallback model."""
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    for model in [_PRIMARY_MODEL, _FALLBACK_MODEL]:
        try:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            r = requests.post(_BASE_URL, headers=headers, json=payload, timeout=_TIMEOUT)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            logger.warning("Groq %s returned %s: %s", model, r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("Groq %s error: %s", model, e)
    raise RuntimeError("Groq API unavailable")


class LLMRouter:

    class _Client:
        """Shim so ask.py can call llm_router.reasoner.chat_completion(...)."""
        def chat_completion(self, messages, max_tokens=500, temperature=0.2, stop=None):
            text = _chat(messages, max_tokens=max_tokens, temperature=temperature)

            class _Msg:
                content = text
            class _Choice:
                message = _Msg()
            class _Resp:
                choices = [_Choice()]
            return _Resp()

    def __init__(self):
        self.extractor = self._Client()
        self.reasoner  = self._Client()

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1)
        brace = re.search(r"\{[\s\S]+\}", text)
        if brace:
            text = brace.group(0)
        return json.loads(text)

    def extract_sla_metrics(self, sla_text: str) -> dict:
        raw = _chat([
            {"role": "system", "content": "You are an SLA data extractor. Return ONLY valid JSON, no explanation."},
            {"role": "user",   "content": f"""Extract SLA metrics from this text. Return ONLY valid JSON:
{{
  "uptime_sla_pct": float or null,
  "rto_hours": float or null,
  "rpo_hours": float or null,
  "support_response_min": int or null,
  "penalty_credit_pct": int or null,
  "regions": ["string"],
  "compliance": ["string"],
  "source_clause": "exact quote"
}}
Text: {sla_text[:2000]}"""},
        ], max_tokens=500, temperature=0)
        return self._parse_json(raw)

    def understand_query(self, query: str) -> dict:
        raw = _chat([
            {"role": "system", "content": "You are a cloud requirements parser. Return ONLY valid JSON, no explanation."},
            {"role": "user",   "content": f"""Extract requirements. Return ONLY valid JSON:
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
Query: {query}"""},
        ], max_tokens=300, temperature=0)
        return self._parse_json(raw)

    def generate_explanation(self, query: str, providers: list, lang: str = "English") -> str:
        return _chat([
            {"role": "system", "content": "You are a cloud SLA analyst. Write concise, factual explanations."},
            {"role": "user",   "content": f"""User requirement: {query}

Ranked providers (with SLA data):
{json.dumps(providers, indent=2)}

Write 3-5 sentences explaining the ranking, citing specific SLA metrics.
Respond in {lang}."""},
        ], max_tokens=400, temperature=0.3)

    def describe_sla_change(self, old_chunk: str, new_chunk: str) -> dict:
        raw = _chat([
            {"role": "system", "content": "You are an SLA change analyst. Return ONLY valid JSON."},
            {"role": "user",   "content": f"""Compare these SLA excerpts. Return ONLY valid JSON:
{{
  "description": "one sentence",
  "change_type": "UPTIME_REDUCED|UPTIME_IMPROVED|RTO_INCREASED|RTO_REDUCED|PENALTY_REDUCED|PENALTY_INCREASED|REGION_REMOVED|COMPLIANCE_REMOVED|WORDING_CHANGE|OTHER",
  "severity": "LOW|MEDIUM|HIGH|CRITICAL|POSITIVE"
}}
Old: {old_chunk[:500]}
New: {new_chunk[:500]}"""},
        ], max_tokens=200, temperature=0)
        return self._parse_json(raw)


llm_router = LLMRouter()
