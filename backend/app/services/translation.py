"""
Translation service — language detection only.

The embedding model (intfloat/multilingual-e5-base) is natively multilingual,
so translation before embedding is unnecessary. Language detection is kept
so the pipeline can tag responses with the detected language.
"""

from langdetect import detect, LangDetectException


def detect_language(text: str) -> str:
    """Detect language code of input text. Returns 'en' on failure."""
    try:
        return detect(text)
    except LangDetectException:
        return "en"


def to_english(text: str) -> tuple[str, str]:
    """
    Detect language and return the text as-is.
    The multilingual-e5 model handles all languages natively.
    Returns (text, detected_lang_code).
    """
    lang = detect_language(text)
    return text, lang
