"""Автотесты Settings: CSV-парсинг CORS_ORIGINS (shell-safe формат)."""

import pytest
from app.config import Settings


def _settings(**kwargs: object) -> Settings:
    return Settings(jwt_secret="test-secret", **kwargs)  # type: ignore[arg-type]


def test_cors_origins_parses_csv() -> None:
    s = _settings(cors_origins="http://a.test,http://b.test")
    assert s.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_strips_whitespace_and_empties() -> None:
    s = _settings(cors_origins=" http://a.test , http://b.test ,")
    assert s.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_list_passthrough() -> None:
    s = _settings(cors_origins=["http://a.test"])
    assert s.cors_origins == ["http://a.test"]


def test_cors_origins_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    s = _settings()
    assert "http://localhost:5173" in s.cors_origins


def test_cors_origins_parses_csv_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Регрессия: EnvSettingsSource декодирует list[str] как JSON ДО validator'а;
    # без NoDecode CSV-строка из env роняет Settings() на старте
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")
    s = Settings(jwt_secret="test-secret")
    assert s.cors_origins == ["http://a.test", "http://b.test"]
