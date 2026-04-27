"""
Unit tests for APIClient — mocked aiohttp, no network calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anyio

from api_client import APIClient


pytestmark = pytest.mark.unit


def _make_mock_response(status=200, body=None, text=None):
    """Create a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    if text is not None:
        resp.text = AsyncMock(return_value=text)
    elif body is not None:
        resp.text = AsyncMock(return_value=json.dumps(body))
    else:
        resp.text = AsyncMock(return_value="{}")
    return resp


def _patch_session(mock_response):
    """Patch aiohttp.ClientSession to return the given mock response."""
    mock_post = AsyncMock(return_value=mock_response)
    # Make the response work as an async context manager
    mock_post.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_post)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    return patch("aiohttp.ClientSession", return_value=mock_session)


class TestAPIClient:

    def test_url_construction(self):
        client = APIClient(base_url="http://localhost:8089/", enable_auth=False)
        assert client.base_url == "http://localhost:8089"

        client2 = APIClient(base_url="http://localhost:8089", enable_auth=False)
        assert client2.base_url == "http://localhost:8089"

    def test_local_mode_routes_fin_engine_to_service_base_url(self):
        client = APIClient(
            base_url="http://localhost:9999",
            local_mode=True,
            service_base_urls={"fin-engine": "http://localhost:8080/"},
        )

        assert client._resolve_url("/cr/fin-engine/financial_engine") == (
            "http://localhost:8080/financial_engine"
        )

    def test_local_mode_routes_model_portfolio_to_service_base_url(self):
        client = APIClient(
            base_url="http://localhost:9999",
            local_mode=True,
            service_base_urls={"model-portfolio": "http://localhost:8081/"},
        )

        assert client._resolve_url("/cr/model-portfolio/get_portfolio_options") == (
            "http://localhost:8081/get_portfolio_options"
        )

    def test_local_mode_service_base_url_falls_back_to_default_base_url(self):
        client = APIClient(base_url="http://localhost:8089", local_mode=True)

        assert client._resolve_url("/cr/fin-engine/financial_engine") == (
            "http://localhost:8089/financial_engine"
        )

    def test_non_local_mode_keeps_deployed_service_prefix(self):
        client = APIClient(
            base_url="https://api.askmyfi.dev",
            local_mode=False,
            service_base_urls={"fin-engine": "http://localhost:8080"},
        )

        assert client._resolve_url("/cr/fin-engine/financial_engine") == (
            "https://api.askmyfi.dev/cr/fin-engine/financial_engine"
        )

    def test_successful_post(self):
        client = APIClient(base_url="http://localhost:8089", enable_auth=False)
        expected = {"funds": [{"name": "SBI Large Cap"}]}
        mock_resp = _make_mock_response(status=200, body=expected)

        with _patch_session(mock_resp):
            result = anyio.run(client.call_tool, "/cr/src/get_query_data", {"query": "test"})

        assert result == expected

    def test_http_error_returns_error_dict(self):
        client = APIClient(base_url="http://localhost:8089", enable_auth=False)
        mock_resp = _make_mock_response(status=500, text="Internal Server Error")

        with _patch_session(mock_resp):
            result = anyio.run(client.call_tool, "/cr/src/get_query_data", {})

        assert "error" in result
        assert result["status_code"] == 500

    def test_http_404_returns_error_dict(self):
        client = APIClient(base_url="http://localhost:8089", enable_auth=False)
        mock_resp = _make_mock_response(status=404, text="Not Found")

        with _patch_session(mock_resp):
            result = anyio.run(client.call_tool, "/unknown/endpoint", {})

        assert result["error"] == "HTTP 404"
        assert result["status_code"] == 404

    def test_non_json_response_returns_result_text(self):
        client = APIClient(base_url="http://localhost:8089", enable_auth=False)
        mock_resp = _make_mock_response(status=200, text="plain text response")

        with _patch_session(mock_resp):
            result = anyio.run(client.call_tool, "/cr/src/get_query_data", {})

        assert "result" in result
        assert result["result"] == "plain text response"

    def test_connection_error_returns_error_dict(self):
        import aiohttp

        client = APIClient(base_url="http://localhost:8089", enable_auth=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("Connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = anyio.run(client.call_tool, "/cr/src/get_query_data", {})

        assert "error" in result
        assert "Connection error" in result["error"]

    def test_timeout_returns_error_dict(self):
        client = APIClient(base_url="http://localhost:8089", enable_auth=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=TimeoutError())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = anyio.run(client.call_tool, "/cr/src/get_query_data", {})

        assert "error" in result
        assert "timed out" in result["error"]

    def test_auth_disabled_no_auth_headers(self):
        client = APIClient(base_url="http://localhost:8089", enable_auth=False)
        result = anyio.run(client._get_auth_headers, "http://localhost:8089/test")
        assert result == {}
