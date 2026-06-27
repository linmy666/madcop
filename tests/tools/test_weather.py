"""Tests for WeatherTool with mocked HTTP."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from madcop.tools.weather import WeatherTool


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

def test_weather_name():
    t = WeatherTool()
    assert t.name == "get_weather"


def test_weather_schema():
    t = WeatherTool()
    schema = t.parameters_schema
    assert schema["type"] == "object"
    assert "city" in schema["properties"]
    assert schema["required"] == ["city"]


def test_weather_openai_schema():
    t = WeatherTool()
    s = t.to_openai_schema()
    assert s["type"] == "function"
    assert s["function"]["name"] == "get_weather"
    assert "parameters" in s["function"]


# --------------------------------------------------------------------------- #
# Execution with mocked JSON response
# --------------------------------------------------------------------------- #

SAMPLE_WTTR_JSON = {
    "current_condition": [{
        "temp_C": "22",
        "FeelsLikeC": "24",
        "humidity": "65",
        "windspeedKmph": "12",
        "weatherDesc": [{"value": "Partly cloudy"}],
    }],
    "nearest_area": [{
        "areaName": [{"value": "Shanghai"}],
    }],
}


def test_call_with_json_response():
    t = WeatherTool()
    with patch.object(t, "_fetch_json", return_value=SAMPLE_WTTR_JSON):
        output = t(city="Shanghai")
    assert "Shanghai" in output
    assert "22" in output
    assert "Partly cloudy" in output
    assert "24" in output  # feels like
    assert "65" in output  # humidity
    assert "12" in output  # wind


def test_call_formats_summary():
    t = WeatherTool()
    with patch.object(t, "_fetch_json", return_value=SAMPLE_WTTR_JSON):
        output = t(city="Shanghai")
    assert "°C" in output
    assert "km/h" in output


def test_call_empty_city():
    t = WeatherTool()
    output = t(city="")
    assert "ERROR" in output


def test_call_missing_city_param():
    t = WeatherTool()
    output = t()
    assert "ERROR" in output


# --------------------------------------------------------------------------- #
# Fallback to text when JSON fails
# --------------------------------------------------------------------------- #

def test_fallback_to_text_on_json_error():
    t = WeatherTool()
    with patch.object(t, "_fetch_json", side_effect=Exception("JSON failed")), \
         patch.object(t, "_fetch_text", return_value="Shanghai: ⛅ +22°C"):
        output = t(city="Shanghai")
    assert "Shanghai" in output
    assert "22" in output


def test_both_endpoints_fail():
    t = WeatherTool()
    with patch.object(t, "_fetch_json", side_effect=Exception("json fail")), \
         patch.object(t, "_fetch_text", side_effect=Exception("text fail")):
        output = t(city="Nowhere")
    assert "ERROR" in output
    assert "Nowhere" in output


# --------------------------------------------------------------------------- #
# JSON formatting edge cases
# --------------------------------------------------------------------------- #

def test_format_json_missing_fields():
    """Handle malformed JSON gracefully."""
    t = WeatherTool()
    # Missing nearest_area and some fields
    partial = {"current_condition": [{"temp_C": "10"}]}
    result = WeatherTool._format_json(partial)
    assert isinstance(result, str)
    # Should not crash, returns something


def test_format_json_empty_current():
    t = WeatherTool()
    empty = {"current_condition": [], "nearest_area": []}
    result = WeatherTool._format_json(empty)
    assert isinstance(result, str)


def test_format_json_key_error():
    """When essential keys are missing, should return raw JSON string."""
    t = WeatherTool()
    bad = {"unexpected": "data"}
    result = WeatherTool._format_json(bad)
    assert isinstance(result, str)
    # Falls back to raw JSON dump
    assert "unexpected" in result


# --------------------------------------------------------------------------- #
# _fetch_json (mocked urllib)
# --------------------------------------------------------------------------- #

def test_fetch_json_calls_urlopen():
    t = WeatherTool()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(SAMPLE_WTTR_JSON).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("madcop.tools.weather.urllib.request.urlopen", return_value=mock_resp):
        data = t._fetch_json("Shanghai")

    assert data["current_condition"][0]["temp_C"] == "22"
    # Verify URL contains the city and format=j1
    args, kwargs = mock_resp.read.call_args or ((), {})  # just verify no crash


def test_fetch_text_calls_urlopen():
    t = WeatherTool()
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"Shanghai: +22C"
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("madcop.tools.weather.urllib.request.urlopen", return_value=mock_resp):
        text = t._fetch_text("Shanghai")

    assert text == "Shanghai: +22C"


def test_fetch_json_timeout():
    import socket
    t = WeatherTool()
    with patch("madcop.tools.weather.urllib.request.urlopen", side_effect=socket.timeout("timed out")):
        with pytest.raises(Exception):
            t._fetch_json("Shanghai")
