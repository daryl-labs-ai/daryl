"""Suite-wide fixtures.

DarylAgent runs in key_protection="production" by default and refuses to
start without a signing secret. Provide a test secret through the
environment so every test exercises the production path; tests that check the
no-secret behaviour remove it with monkeypatch.delenv.
"""

import pytest


@pytest.fixture(autouse=True)
def _dsm_signing_secret(monkeypatch):
    monkeypatch.setenv("DSM_SIGNING_PASSWORD", "test-only-signing-secret")
    monkeypatch.delenv("DSM_KEY_PROTECTION", raising=False)
