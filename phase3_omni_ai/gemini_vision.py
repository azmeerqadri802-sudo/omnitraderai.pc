"""Gemini chart-image analysis using the explicitly requested legacy SDK."""

from __future__ import annotations

import json
import os
from typing import Any

import google.generativeai as genai
from PIL import Image

from phase4_binance_engine.credential_store import get_secret
from .image_processor import process_chart_image


DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
SYSTEM_PROMPT = """You are Omni AI, a disciplined chart analyst using day-trading terminology.
Analyze only visible information in this static chart: trend, price action,
support/resistance, and recognizable candle/chart patterns. Do not invent
prices, instruments, indicators, or timeframes. If labels or the price scale
are unclear, choose Hold and set both prices to N/A. Otherwise choose Buy only
for a clearly bullish setup, Sell only for a clearly bearish setup, and Hold
when the setup is uncertain. Return ONLY one strict JSON object with exactly
these keys: Action, Open_Price, Close_Price, Reason. Action must be Buy, Sell,
or Hold. All values must be strings. For Buy/Sell, prices must be positive
plain decimal strings without commas, currency signs, or units. A Buy target
must exceed its entry; a Sell target must be below its entry. Keep Reason under
35 words. This is an interpretation of a static image, not a live quote,
guarantee, personalized financial advice, or a verified order instruction."""

REQUIRED_FIELDS = {"Action", "Open_Price", "Close_Price", "Reason"}


def _validate_response(text: str) -> dict[str, str]:
    try:
        value: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini did not return valid JSON. Try a clearer chart image.") from exc
    if not isinstance(value, dict) or set(value) != REQUIRED_FIELDS:
        raise RuntimeError("Gemini response did not match the required four-field JSON schema.")
    if any(not isinstance(value[key], str) for key in REQUIRED_FIELDS):
        raise RuntimeError("Gemini response fields must all be strings.")
    if value["Action"] not in {"Buy", "Sell", "Hold"}:
        raise RuntimeError("Gemini Action must be Buy, Sell, or Hold.")
    return {key: value[key].strip() for key in REQUIRED_FIELDS}


class GeminiVisionAnalyzer:
    """Upload a normalized Pillow image to Gemini and return validated JSON."""

    def __init__(self, api_key: str | None = None, model_name: str = DEFAULT_MODEL) -> None:
        key = (api_key or get_secret("GEMINI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("Save a Gemini API key in Settings before analyzing charts.")
        genai.configure(api_key=key)
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT,
            generation_config={
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        )

    def analyze_image(self, image: Image.Image) -> dict[str, str]:
        prepared = process_chart_image(image)
        response = self.model.generate_content(
            ["Analyze this candlestick chart screenshot and return the required JSON.", prepared],
            request_options={"timeout": 60},
        )
        response_text = getattr(response, "text", None)
        if not response_text:
            raise RuntimeError("Gemini returned no text. The image may have been blocked or unclear.")
        return _validate_response(response_text)

    def analyze_file(self, path: str | Path) -> dict[str, str]:
        return self.analyze_image(process_chart_image(path))
