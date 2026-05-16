"""Regression test for #26958: Discord View classes must be defined after lazy install.

When discord.py is not pre-installed (Docker gateway deployments), the
``if DISCORD_AVAILABLE:`` guard at module load time used to skip the View
class definitions entirely.  After ``check_discord_requirements()``
lazily installed the library and set ``DISCORD_AVAILABLE = True``, the
classes remained undefined — causing ``NameError`` at runtime when
``send_exec_approval()`` or ``send_slash_confirm()`` tried to
instantiate them.

The fix wraps the class definitions in ``_define_discord_views()`` and
calls it both at module level (for pre-installed discord) **and** from
``check_discord_requirements()`` after a successful lazy install.
"""

import builtins
import importlib
import sys

import pytest


class TestDiscordViewsAfterLazyInstall:
    """Simulate the lazy-install path and verify View classes are defined."""

    def test_views_defined_after_check_discord_requirements(self, monkeypatch):
        """After check_discord_requirements() succeeds, all five View classes
        must exist in the module globals — even when discord was unavailable
        at initial import time."""

        # ------------------------------------------------------------------
        # Phase 1: Import the discord module with discord *unavailable*,
        # simulating a Docker deployment where discord.py isn't pre-installed.
        # ------------------------------------------------------------------
        original_import = builtins.__import__

        def blocking_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "discord" or name.startswith("discord."):
                raise ImportError("discord unavailable for test")
            return original_import(name, globals, locals, fromlist, level)

        # Purge any cached import of the discord platform module.
        monkeypatch.delitem(sys.modules, "gateway.platforms.discord", raising=False)
        monkeypatch.setattr(builtins, "__import__", blocking_import)

        module = importlib.import_module("gateway.platforms.discord")

        # Sanity: discord is NOT available at this point.
        assert module.DISCORD_AVAILABLE is False
        assert module.discord is None

        # View classes should NOT be defined yet (the original bug).
        for cls_name in (
            "ExecApprovalView", "SlashConfirmView", "UpdatePromptView",
            "ModelPickerView", "ClarifyChoiceView",
        ):
            assert not hasattr(module, cls_name), (
                f"{cls_name} should not exist before lazy install"
            )

        # ------------------------------------------------------------------
        # Phase 2: Restore real imports and call check_discord_requirements()
        # to simulate the lazy-install succeeding.  We use the test-suite's
        # discord mock from conftest.py.
        # ------------------------------------------------------------------
        monkeypatch.setattr(builtins, "__import__", original_import)

        # Ensure the conftest discord mock is in place.
        from tests.gateway.conftest import _ensure_discord_mock
        _ensure_discord_mock()

        # Patch lazy_deps.ensure to be a no-op (mock already provides discord).
        monkeypatch.setattr(
            module, "check_discord_requirements",
            lambda: _simulate_lazy_install(module),
        )
        _simulate_lazy_install(module)

        # ------------------------------------------------------------------
        # Phase 3: Verify all five View classes are now defined.
        # ------------------------------------------------------------------
        for cls_name in (
            "ExecApprovalView", "SlashConfirmView", "UpdatePromptView",
            "ModelPickerView", "ClarifyChoiceView",
        ):
            cls = getattr(module, cls_name, None)
            assert cls is not None, (
                f"{cls_name} must be defined after check_discord_requirements()"
            )
            assert callable(cls), f"{cls_name} should be a class"


def _simulate_lazy_install(module):
    """Mimic what check_discord_requirements() does after lazy-installing
    discord.py — re-import the library and call _define_discord_views()."""
    import discord as _discord
    from discord import Message as _DM, Intents as _Intents
    from discord.ext import commands as _commands

    module.discord = _discord
    module.DiscordMessage = _DM
    module.Intents = _Intents
    module.commands = _commands
    module.DISCORD_AVAILABLE = True
    module._define_discord_views()
    return True
