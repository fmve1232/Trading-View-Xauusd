"""Execution mode, versioning, providers. Sections 44, 57, 63, 65, 66, 83."""

from __future__ import annotations

import pytest

from quantum_institutional.data.providers.base import MarketDataProvider, NewsProvider
from quantum_institutional.data.providers.registry import _REGISTRY, register, resolve, resolve_market
from quantum_institutional.errors import DataUnavailable
from quantum_institutional.execution.mode import ExecutionMode
from quantum_institutional.version import current_stamp


class TestExecutionMode:
    def test_default_is_paper(self) -> None:
        assert ExecutionMode.from_env(None) is ExecutionMode.PAPER
        assert ExecutionMode.from_env("") is ExecutionMode.PAPER

    def test_live_requires_the_exact_word(self) -> None:
        assert ExecutionMode.from_env("LIVE") is ExecutionMode.LIVE
        assert ExecutionMode.from_env(" live ") is ExecutionMode.LIVE

    @pytest.mark.parametrize("value", ["LIVE_TEST", "live-ish", "production", "1", "true", "PAPERTRADE"])
    def test_unrecognised_values_raise_rather_than_defaulting(self, value: str) -> None:
        """A typo must stop the deploy, not silently pick a mode.

        Defaulting to PAPER would be the safe direction but the wrong
        behaviour: it hides a broken config until someone expects live orders.
        """
        with pytest.raises(ValueError, match="Refusing to guess"):
            ExecutionMode.from_env(value)

    def test_only_live_places_orders(self) -> None:
        assert not ExecutionMode.PAPER.places_orders
        assert ExecutionMode.LIVE.places_orders


class TestVersionStamp:
    def test_stamp_carries_every_section_57_field(self) -> None:
        stamp = current_stamp(model_version="m1", data_version="d1")
        for field in ("engine_version", "formula_registry_version", "schema_version"):
            assert getattr(stamp, field)
        assert stamp.model_version == "m1"
        assert stamp.data_version == "d1"

    def test_unknown_commit_is_none_not_a_placeholder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A fabricated hash would make an irreproducible result look reproducible."""
        from quantum_institutional import version as version_module

        version_module._git_commit.cache_clear()
        monkeypatch.delenv("GIT_COMMIT", raising=False)
        monkeypatch.delenv("GITHUB_SHA", raising=False)

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise OSError

        monkeypatch.setattr(version_module.subprocess, "run", _raise)
        try:
            stamp = version_module.current_stamp()
            assert stamp.git_commit is None
            assert stamp.is_reproducible is False
        finally:
            version_module._git_commit.cache_clear()

    def test_injected_commit_is_preferred(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Build artefacts have no .git directory; CI injects the SHA."""
        from quantum_institutional import version as version_module

        version_module._git_commit.cache_clear()
        monkeypatch.setenv("GIT_COMMIT", "deadbeef")
        try:
            assert version_module.current_stamp().git_commit == "deadbeef"
        finally:
            version_module._git_commit.cache_clear()


class TestProviderRegistry:
    def test_no_providers_ship_with_the_repository(self) -> None:
        """Section 83: a stub returning plausible prices is fabricated data."""
        assert _REGISTRY == {}

    def test_unregistered_name_raises_data_unavailable(self) -> None:
        with pytest.raises(DataUnavailable, match="no provider registered"):
            resolve_market("does_not_exist")

    def test_wrong_provider_kind_fails_at_resolution(self) -> None:
        """A news provider in the market slot must fail at startup, not on use."""

        class FakeNews(NewsProvider):
            @property
            def name(self) -> str:
                return "fake_news"

            def health(self) -> bool:
                return True

            def get_news(self, start, end, symbols=None):  # type: ignore[no-untyped-def]
                return []

        register("fake_news", FakeNews)
        try:
            with pytest.raises(TypeError, match="expected MarketDataProvider"):
                resolve("fake_news", MarketDataProvider)
        finally:
            _REGISTRY.pop("fake_news", None)

    def test_duplicate_registration_raises(self) -> None:
        """Silent replacement lets import order swap the live data source."""

        class FakeNews(NewsProvider):
            @property
            def name(self) -> str:
                return "dup"

            def health(self) -> bool:
                return True

            def get_news(self, start, end, symbols=None):  # type: ignore[no-untyped-def]
                return []

        register("dup", FakeNews)
        try:
            with pytest.raises(ValueError, match="already registered"):
                register("dup", FakeNews)
        finally:
            _REGISTRY.pop("dup", None)
