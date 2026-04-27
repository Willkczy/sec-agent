"""
Async HTTP client for calling securities-recommendation microservice endpoints.
"""

import json
import re
from typing import Any

import aiohttp


class APIClient:
    """Simple async HTTP client for calling the securities-recommendation APIs."""

    # Prefixes added by the reverse proxy in deployed environments.
    # In local_mode we strip them so the request goes straight to a service
    # bound on its own port with no proxy in front.
    _SERVICE_PREFIX_RE = re.compile(r"^/cr/(src|fin-engine|model-portfolio|mlr)")

    def __init__(
        self,
        base_url: str,
        enable_auth: bool = False,
        local_mode: bool = False,
        timeout: int = 60,
        service_base_urls: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.enable_auth = enable_auth
        self.local_mode = local_mode
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.service_base_urls = {
            service: url.rstrip("/")
            for service, url in (service_base_urls or {}).items()
            if url
        }

    def _resolve_url(self, endpoint: str) -> str:
        """Resolve a tool endpoint to its final URL."""
        base_url = self.base_url

        if self.local_mode:
            match = self._SERVICE_PREFIX_RE.match(endpoint)
            if match:
                service = match.group(1)
                base_url = self.service_base_urls.get(service, self.base_url)
                endpoint = self._SERVICE_PREFIX_RE.sub("", endpoint, count=1)

        return base_url + endpoint

    async def _get_auth_headers(self, url: str) -> dict[str, str]:
        """Get S2S authentication headers for deployed environments."""
        if not self.enable_auth:
            return {}
        try:
            # Import only when auth is needed (avoids dependency on MCS packages locally)
            from shared.utils.auth import Authenticator

            return await Authenticator.get_s2s_id_token(url)
        except ImportError:
            return {}

    async def call_tool(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Make an async POST request to a microservice endpoint.

        Args:
            endpoint: API path (e.g., "/cr/src/get_query_data")
            params: Request body as dict

        Returns:
            JSON response as dict, or error dict on failure.
        """
        url = self._resolve_url(endpoint)
        headers = {"Content-Type": "application/json"}
        headers.update(await self._get_auth_headers(url))

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, json=params, headers=headers) as resp:
                    body = await resp.text()
                    if resp.status >= 400:
                        return {
                            "error": f"HTTP {resp.status}",
                            "status_code": resp.status,
                            "detail": body[:2000],
                        }
                    try:
                        return json.loads(body)
                    except json.JSONDecodeError:
                        return {"result": body[:2000]}
        except aiohttp.ClientError as e:
            return {"error": f"Connection error: {str(e)}"}
        except TimeoutError:
            return {"error": f"Request timed out after {self.timeout.total}s"}
