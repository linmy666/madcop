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


# Common Chinese → English city name mappings. llama-3.1-8b-instruct
# often hallucinates Chinese city names (e.g. sends "王州" instead of
# "杭州") — we strip the request and try both the original and the
# pinyin name to maximize the chance of a successful API call.
_CHINESE_CITY_MAP: dict[str, str] = {
    "杭州": "Hangzhou",
    "上海": "Shanghai",
    "北京": "Beijing",
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "南京": "Nanjing",
    "苏州": "Suzhou",
    "成都": "Chengdu",
    "重庆": "Chongqing",
    "武汉": "Wuhan",
    "西安": "Xi'an",
    "天津": "Tianjin",
    "长沙": "Changsha",
    "青岛": "Qingdao",
    "厦门": "Xiamen",
    "宁波": "Ningbo",
    "香港": "Hong Kong",
    "台北": "Taipei",
}


def _resolve_city(city: str) -> list[str]:
    """Return a list of city-name variants to try, in priority order.

    If the input is a known Chinese city name, we try:
      1. the original Chinese name (wttr.in accepts it)
      2. the English/pinyin name from the lookup table
    Otherwise we just return [city].
    """
    city = city.strip()
    candidates = [city]
    if city in _CHINESE_CITY_MAP:
        candidates.append(_CHINESE_CITY_MAP[city])
    return candidates


class WeatherTool(Tool):
    """Return the current weather for a given city.

    Uses the free wttr.in service (no API key).  Falls back to a
    short text summary when the JSON endpoint is unavailable.
    """

    name = "get_weather"
    description = (
        "Get the current weather for a city. "
        "Returns temperature, condition, and a short description. "
        "ALWAYS pass the city name in English (e.g. 'Hangzhou', 'Shanghai', "
        "'New York', 'London'). Do NOT pass Chinese characters — the API "
        "may fail to recognize them."
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
                    "description": (
                        "City name in English (pinyin for Chinese cities). "
                        "Examples: 'Hangzhou', 'Shanghai', 'Beijing', "
                        "'New York', 'London', 'Tokyo'."
                    ),
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
        """Fetch weather, preferring the JSON endpoint, falling back to text.

        Tries each candidate city name (e.g. both 杭州 and Hangzhou)
        and returns the first successful response.
        """
        candidates = _resolve_city(city)
        last_error: str = ""
        for candidate in candidates:
            try:
                data = self._fetch_json(candidate)
                return self._format_json(data)
            except Exception as e:
                last_error = f"json endpoint for '{candidate}': {e}"
            try:
                return self._fetch_text(candidate)
            except Exception as e:  # noqa: BLE001
                last_error = f"text endpoint for '{candidate}': {e}"
                continue
        return (
            f"ERROR: could not fetch weather for '{city}' "
            f"(tried {len(candidates)} variant(s)). Last error: {last_error}"
        )

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
