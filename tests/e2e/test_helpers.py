"""
Unit tests para `tests/e2e/helpers.py` -- funciones puras, sin red ni
servidor (no requieren marker, corren en cualquier `pytest`).
"""
import pytest

from tests.e2e.helpers import (
    LOCAL_CHAT_BASE_URL,
    PROD_CHAT_BASE_URL,
    resolve_chat_base_url,
    resolve_e2e_target,
)


@pytest.fixture(autouse=True)
def _clean_target_env(monkeypatch):
    monkeypatch.delenv("PULPO_E2E_TARGET", raising=False)


def test_resolve_e2e_target_defaults_to_local():
    assert resolve_e2e_target() == "local"


def test_resolve_e2e_target_reads_env(monkeypatch):
    monkeypatch.setenv("PULPO_E2E_TARGET", "prod")
    assert resolve_e2e_target() == "prod"


def test_resolve_e2e_target_is_case_and_whitespace_insensitive(monkeypatch):
    monkeypatch.setenv("PULPO_E2E_TARGET", "  PROD  ")
    assert resolve_e2e_target() == "prod"


def test_resolve_e2e_target_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("PULPO_E2E_TARGET", "staging")
    with pytest.raises(ValueError):
        resolve_e2e_target()


def test_resolve_chat_base_url_defaults_to_local():
    assert resolve_chat_base_url() == LOCAL_CHAT_BASE_URL


def test_resolve_chat_base_url_prod(monkeypatch):
    monkeypatch.setenv("PULPO_E2E_TARGET", "prod")
    assert resolve_chat_base_url() == PROD_CHAT_BASE_URL
