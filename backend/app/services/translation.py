"""
Translation service using LibreTranslate (self-hosted).
"""

import requests
from langdetect import detect, LangDetectException

from app.core.config import settings


def detect_language(text: str) -> str:
    """Detect language code of input text. Returns 'en' on failure."""
    try:
        return detect(text)
    except LangDetectException:
        return "en"


def translate(text: str, source: str, target: str) -> str:
    """
    Translate text using LibreTranslate.
    Returns original text on failure (graceful degradation).
    """
    if source == target:
        return text
    try:
        response = requests.post(
            f"{settings.libretranslate_url}/translate",
            json={"q": text, "source": source, "target": target},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["translatedText"]
    except Exception:
        # Graceful fallback: return original text
        return text


def to_english(text: str) -> tuple[str, str]:
    """
    Detect language, translate to English if needed.
    Returns (english_text, detected_lang_code).
    """
    lang = detect_language(text)
    if lang == "en":
        return text, lang
    return translate(text, source=lang, target="en"), lang
