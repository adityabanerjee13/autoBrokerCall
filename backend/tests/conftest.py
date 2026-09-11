import pytest

import app.db as dbmod


@pytest.fixture(autouse=True)
def fresh_motor_client():
    """Rebuild the motor client for every test.

    The client is cached at module level and binds to the event loop that first
    used it. pytest-asyncio gives each test its own loop, so a cached client
    from a previous test looks like an unreachable database rather than a
    programming error - which is exactly how these tests started silently
    skipping.
    """
    dbmod._client = None
    yield
    if dbmod._client is not None:
        dbmod._client.close()
    dbmod._client = None
