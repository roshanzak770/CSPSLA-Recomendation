"""
LLM Router — Groq API (llama-3.1-8b-instant).

Free tier: 14,400 requests/day, 30 req/min.
Fallback: llama-3.2-3b-preview if primary is rate-limited.
"""

import json
import re
import time
import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL      = "https://api.groq.com/openai/v1/chat/completions"
# Primary: best general-purpose Groq instant model as of 2026.
# Fallbacks: try the larger 70B then the supersmall 8B variant if the primary
# is rate-limited. Both are currently active on Groq's free tier.
# (llama-3.2-3b-preview was decommissioned in mid-2026 — do not put it back.)
_MODEL_CHAIN = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
]
_TIMEOUT = 30
_RATE_LIMIT_BACKOFF_SEC = 8   # Groq TPM resets per minute; ~8s usually clears it


# ---------------------------------------------------------------------------
# Helpers used by extract_sla_metrics() — kept at module level so they can be
# unit-tested in isolation without spinning up the LLM client.
# ---------------------------------------------------------------------------

# Sane ranges for each numeric field. Anything outside gets dropped to None.
# These are deliberately generous — we only want to catch obvious extraction
# misreads (e.g. "99" as uptime when the document actually said "99.99"),
# not to police the data.
_METRIC_BOUNDS = {
    "uptime_sla_pct":       (95.0, 100.0),     # below 95 = misread; above 100 = nonsense
    "rto_hours":            (0.0,  168.0),     # 0–7 days
    "rpo_hours":            (0.0,  168.0),
    "support_response_min": (1,    1440),      # 1 min – 24 h
    # Cap at 50% — vendors publish tiered credits topping out around 30% in
    # practice. The LLM otherwise tends to read "100% Service Credit"
    # (the catastrophic-outage tier) as the headline, which inflates rankings.
    "penalty_credit_pct":   (0,    50),
}


def _smart_sample(text: str, target_chars: int = 9000) -> str:
    """Pull head + middle + tail slices so the LLM sees actual SLA content
    rather than just the cover page / table of contents. Short documents
    are returned whole.

    Why this matters: a 50-page Oracle PaaS PDF has TOC and definitions for
    the first ~20 pages, then the real SLA tables — the old [:2000] slice
    never reached them. The middle slice catches those tables; the tail
    slice catches appendices (compliance lists, region maps) that vendors
    often park at the back.
    """
    if not text:
        return ""
    text = text.replace("\r", "")
    if len(text) <= target_chars:
        return text

    third = target_chars // 3
    head = text[:third]
    # Middle slice anchored at the document midpoint
    mid_start = max(third, (len(text) // 2) - (third // 2))
    middle = text[mid_start:mid_start + third]
    tail = text[-third:]

    return (
        head
        + "\n\n[…document continues…]\n\n"
        + middle
        + "\n\n[…document continues…]\n\n"
        + tail
    )


def _validate_metrics(parsed: dict) -> dict:
    """Drop nonsense values to None so they trigger curated fallback rather
    than poisoning TOPSIS. Returns a dict shaped like the original."""
    if not isinstance(parsed, dict):
        return {}
    out: dict = {}
    for field, (lo, hi) in _METRIC_BOUNDS.items():
        v = parsed.get(field)
        if v is None:
            out[field] = None
            continue
        try:
            num = float(v)
        except (TypeError, ValueError):
            out[field] = None
            continue
        if num < lo or num > hi:
            out[field] = None
            continue
        # Preserve int-ness for the integer fields
        out[field] = int(num) if isinstance(_METRIC_BOUNDS[field][0], int) else num

    # Pass through list fields with shallow sanitisation
    regions = parsed.get("regions") or []
    compliance = parsed.get("compliance") or []
    out["regions"]    = [r.strip() for r in regions    if isinstance(r, str) and r.strip()]
    out["compliance"] = [c.strip() for c in compliance if isinstance(c, str) and c.strip()]
    out["source_clause"] = parsed.get("source_clause")
    return out


def _chat(messages: list, max_tokens: int = 500, temperature: float = 0.1) -> str:
    """Call Groq chat completions. Walks the model chain in order, and
    on a 429 (rate limit) sleeps briefly and retries the SAME model once
    before falling through to the next one. Groq's TPM resets per minute,
    so a short backoff is usually enough."""
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    for model in _MODEL_CHAIN:
        for attempt in range(2):  # one retry per model on rate-limit
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
                if r.status_code == 429 and attempt == 0:
                    logger.info("Groq %s rate-limited, sleeping %ss and retrying once",
                                model, _RATE_LIMIT_BACKOFF_SEC)
                    time.sleep(_RATE_LIMIT_BACKOFF_SEC)
                    continue
                logger.warning("Groq %s returned %s: %s", model, r.status_code, r.text[:200])
                break  # non-429 error → don't retry, try next model
            except Exception as e:
                logger.warning("Groq %s error: %s", model, e)
                break
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
        """
        Extract structured SLA metrics from raw document text.

        The old version sent only the first 2000 characters, which on most
        real SLA PDFs is the table of contents — values appear deeper in
        the document. This version:

        1. **Smart-samples the text** — head + middle + tail slices so the
           prompt sees the actual SLA tables, not just the cover page.
        2. **Asks for the *highest published* tier** — vendors quote several
           ("99.99% multi-AZ, 99.0% single-AZ"); we want the headline
           commitment, not the lowest fallback.
        3. **Demands null over guesses** — explicit instruction so the LLM
           returns null when a field is genuinely absent, rather than
           hallucinating a number from unrelated text.
        4. **Validates the output** — values outside sensible ranges are
           dropped to null before the caller stores them, so a misread
           99.0 (against AWS's real 99.99) can never poison TOPSIS.
        """
        sample = _smart_sample(sla_text, target_chars=9000)

        prompt = f"""Extract the cloud provider's STRONGEST published SLA commitments from the text below.

Return ONLY this JSON shape (no prose, no markdown fences):
{{
  "uptime_sla_pct":       float | null,   // The HIGHEST uptime % the provider promises for any tier (e.g. multi-AZ EC2 = 99.99). Range: 95.0–100.0.
  "rto_hours":            float | null,   // Recovery Time Objective in HOURS. If quoted in minutes/seconds, convert. Range: 0–168.
  "rpo_hours":            float | null,   // Recovery Point Objective in HOURS. Same conversion rules. Range: 0–168.
  "support_response_min": int   | null,   // Premium/enterprise tier response time in MINUTES. Range: 1–1440.
  "penalty_credit_pct":   int   | null,   // The TYPICAL maximum service credit % published in the SLA's main credit table. Most vendors publish 10–30%. Do NOT pick exotic high values like 100% that only apply to catastrophic-outage tiers. Range: 0–50.
  "regions":              [string],       // Region IDs like "us-east-1", "eastus", "europe-west1". NO descriptions or headers.
  "compliance":           [string],       // Standards like "SOC2", "HIPAA", "GDPR", "FedRAMP", "ISO27001", "PCI-DSS", "FIPS 140-2".
  "source_clause":        string | null   // Up to 200 chars quoted directly from the document supporting the uptime number.
}}

Rules — read carefully:
- If a field is NOT mentioned in the text, return **null** (or empty list for regions/compliance). Do NOT guess.
- For uptime, when the document lists multiple tiers (single-AZ vs multi-AZ, standard vs premium), return the **highest**.
- "Service Credit" / "Service Credits" / "credit percentage" all map to penalty_credit_pct.
- regions must be machine-readable IDs (e.g. "us-east-1") — never marketing phrases like "AWS Region" or "all our locations".
- compliance entries must be standard names — never sentences.
- Do not paraphrase numbers. If text says "99.99%", return 99.99 (not 99 or 100).

Document text:
\"\"\"
{sample}
\"\"\"
"""
        raw = _chat(
            [
                {"role": "system", "content": "You are a meticulous SLA data extractor. Return ONLY valid JSON conforming to the schema. Use null when uncertain."},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=900,
            temperature=0,
        )
        return _validate_metrics(self._parse_json(raw))

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

    def generate_explanation(self, query: str, provider: dict, all_providers: list, lang: str = "English") -> str:
        # Pick a useful comparison anchor: the winner (rank 1). If THIS
        # provider is rank 1, the anchor flips to the closest competitor
        # so the explanation can still say "beat X by Y points on metric Z".
        is_winner = provider.get("rank") == 1
        comparison_anchor = None
        if all_providers:
            if is_winner and len(all_providers) > 1:
                comparison_anchor = all_providers[1]
            elif not is_winner:
                comparison_anchor = all_providers[0]

        service_line = ""
        if provider.get("service"):
            service_line = f"This row represents the **{provider['service']}** service, not the whole {provider['name']} portfolio.\n"

        return _chat([
            {"role": "system", "content": (
                "You are a cloud SLA analyst writing for an engineer who needs to defend a "
                "provider-selection decision. Be specific, comparative, and number-driven. "
                "Never write generic praise like 'strong SLA profile' — name the exact metric "
                "and the exact number. Always reference at least one other provider by name."
            )},
            {"role": "user", "content": f"""User requirement: {query}

All ranked providers (compact profiles):
{json.dumps(all_providers, indent=2)}

Focus provider:
{json.dumps(provider, indent=2)}

{service_line}Write 3-4 sentences explaining why "{provider['name']}" {'won the ranking' if is_winner else f'ranked #{provider.get("rank")}'} with a final score of {provider.get('final_score')}.
Requirements for your answer:
  1. Cite at least TWO specific SLA numbers from the focus provider (e.g. uptime 99.99%, RTO 1h, support 15min, credit 30%).
  2. Compare directly to {comparison_anchor['name'] if comparison_anchor else 'one other provider in the list'} — name the metric where they differ and the numeric gap.
  3. {"Mention what the closest competitor would have to improve to overtake." if is_winner else f"Mention which specific metric pushed the focus provider below rank 1, and by how much (gap_vs_winner = {provider.get('gap_vs_winner')})."}
  4. If `meets_uptime` is false, point that out as a caveat. Don't gloss over weaknesses.
Respond in {lang}. Plain prose, no bullets, no markdown headers."""},
        ], max_tokens=280, temperature=0.25)

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
