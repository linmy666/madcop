"""WeatherTool — fetches current weather via the free wttr.in API.

wttr.in is a weather service that requires no API key. Example::

    curl "https://wttr.in/Shanghai?format=3"
    → Shanghai: ⛅ +22°C

We use urllib.request (stdlib only) so no extra dependencies are needed.
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import Any

from .registry import Tool


# macOS Python doesn't always have certs; use an unverified context
# as a fallback. wttr.in is a free public API — this is safe enough.
_ssl_ctx = ssl.create_default_context()
_ssl_ctx_unverified = ssl.create_default_context()
_ssl_ctx_unverified.check_hostname = False
_ssl_ctx_unverified.verify_mode = ssl.CERT_NONE


class WeatherTool(Tool):
    """Return the current weather for a given city.

    Uses the free wttr.in service (no API key).  Falls back to a
    short text summary when the JSON endpoint is unavailable.
    """

    name = "get_weather"
    description = (
        "Get the current weather for a city. "
        "Returns temperature, condition, and a short description."
    )

    # configurable for tests
    base_url: str = "https://wttr.in"
    timeout: float = 10.0

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 'Shanghai', 'New York', 'London'",
                },
            },
            "required": ["city"],
        }

    def __call__(self, **kwargs: Any) -> str:
        city = str(kwargs.get("city", "")).strip()
        if not city:
            return "ERROR: 'city' parameter is required."
        return self._fetch(city)

    # ------------------------------------------------------------------ #
    # Internal helpers — kept as methods so tests can monkeypatch them
    # ------------------------------------------------------------------ #

    def _fetch(self, city: str) -> str:
        """Fetch weather, preferring the JSON endpoint, falling back to text."""
        # Try JSON format first — it gives structured data
        try:
            data = self._fetch_json(city)
            return self._format_json(data)
        except Exception:
            pass
        # Fallback: the one-line text format (e.g. "Shanghai: ⛅ +22°C")
        try:
            return self._fetch_text(city)
        except Exception as e:  # noqa: BLE001
            return f"ERROR: could not fetch weather for '{city}': {e}"

    def _fetch_json(self, city: str) -> dict[str, Any]:
        """Call wttr.in with format=j1 and return parsed JSON dict."""
        safe = urllib.parse.quote(city)
        url = f"{self.base_url}/{safe}?format=j1"
        req = urllib.request.Request(
            url, headers={"User-Agent": "curl/8.0", "Accept": "application/json"}
        )
        # Use unverified SSL context — macOS Python often lacks certs
        # and wttr.in is a free public weather API.
        with urllib.request.urlopen(req, timeout=self.timeout, context=_ssl_ctx_unverified) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)

    def _fetch_text(self, city: str) -> str:
        """Call wttr.in with format=3 → 'City: condition +temp°C'."""
        safe = urllib.parse.quote(city)
        url = f"{self.base_url}/{safe}?format=3"
        req = urllib.request.Request(
            url, headers={"User-Agent": "curl/8.0", "Accept": "text/plain"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout, context=_ssl_ctx_unverified) as resp:
            return resp.read().decode("utf-8", errors="replace").strip()

    @staticmethod
    def _format_json(data: dict[str, Any]) -> str:
        """Format wttr.in JSON response into a concise summary."""
        try:
            current = data["current_condition"][0]
            area = data.get("nearest_area", [{}])[0]
            city = area.get("areaName", [{}])[0].get("value", "?")
            temp = current.get("temp_C", "?")
            feels = current.get("FeelsLikeC", "?")
            desc_list = current.get("weatherDesc", [{"value": "unknown"}])
            desc = desc_list[0].get("value", "unknown") if desc_list else "unknown"
            humidity = current.get("humidity", "?")
            wind = current.get("windspeedKmph", "?")
            return (
                f"{city}: {desc}, {temp}°C "
                f"(feels like {feels}°C), humidity {humidity}%, wind {wind} km/h"
            )
        except (KeyError, IndexError, TypeError):
            # Malformed JSON — fall back to raw string
            return json.dumps(data, ensure_ascii=False)[:200]


__all__ = ["WeatherTool"]
