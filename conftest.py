"""Root conftest — pin async tests to asyncio backend only (not trio)."""

import pytest


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param
