"""
Async HTTP client for calling securities-recommendation microservice endpoints.
"""

import json
import aiohttp
from typing import Any


class APIClient:
    """Simple async HTTP client for calling the securities-recommendation APIs."""

    def __init__(self, base_url: str, enable_auth: bool = False, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.enable_auth = enable_auth
        self.timeout = aiohttp.ClientTimeout(total=timeout)

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
        url = self.base_url + endpoint
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
