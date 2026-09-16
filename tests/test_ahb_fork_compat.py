from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import nodriver
from nodriver import cdp
from nodriver.core import config as config_module
from nodriver.core.element import Element
from nodriver.core.tab import Tab


def test_python_314_generated_sources_are_utf8():
    for path in Path("nodriver/cdp").glob("*.py"):
        path.read_bytes().decode("utf-8")


def test_cookie_parser_tolerates_recent_chrome_omissions():
    cookie = cdp.network.Cookie.from_json(
        {
            "name": "cf_clearance",
            "value": "token",
            "domain": ".example.test",
            "path": "/",
            "size": 5,
            "httpOnly": True,
            "secure": True,
            "session": False,
        }
    )
    assert cookie.priority is cdp.network.CookiePriority.MEDIUM
    assert cookie.source_scheme is cdp.network.CookieSourceScheme.UNSET
    assert cookie.source_port == -1


def test_grant_all_permissions_does_not_require_removed_flash_enum():
    assert not hasattr(cdp.browser.PermissionType, "FLASH")
    excluded = {"FLASH", "CAPTURED_SURFACE_CONTROL"}
    permissions = [p for p in cdp.browser.PermissionType if p.name not in excluded]
    assert permissions
    assert all(p.name not in excluded for p in permissions)


def test_scroll_bottom_reached_accepts_boolean_evaluate_result():
    tab = object.__new__(Tab)

    async def evaluate(*args, **kwargs):
        assert kwargs["return_by_value"] is True
        return True

    tab.evaluate = evaluate
    assert asyncio.run(Tab.scroll_bottom_reached(tab)) is True


def test_element_relative_mouse_drag_is_expanded_once():
    calls = []

    class FakeTab:
        async def mouse_drag(self, source, dest, relative=False, steps=1):
            calls.append((source, dest, relative, steps))

    class FakeElement(Element):
        def __init__(self, tab, center):
            self._tab = tab
            self._center = center

        async def get_position(self):
            return SimpleNamespace(center=self._center)

    element = FakeElement(FakeTab(), (100, 200))
    asyncio.run(element.mouse_drag((10, -5), relative=True, steps=3))
    assert calls == [((100, 200), (10, -5), True, 3)]


def test_element_destination_forces_absolute_drag():
    calls = []

    class FakeTab:
        async def mouse_drag(self, source, dest, relative=False, steps=1):
            calls.append((source, dest, relative, steps))

    class FakeElement(Element):
        def __init__(self, tab, center):
            self._tab = tab
            self._center = center

        async def get_position(self):
            return SimpleNamespace(center=self._center)

    tab = FakeTab()
    source = FakeElement(tab, (100, 200))
    destination = FakeElement(tab, (300, 400))
    asyncio.run(source.mouse_drag(destination, relative=True))
    assert calls == [((100, 200), (300, 400), False, 1)]


def test_find_chrome_executable_honors_path_order(monkeypatch):
    monkeypatch.setattr(config_module, "is_posix", True)
    monkeypatch.setenv("PATH", "/preferred:/fallback")

    def exists(path):
        return path in {"/preferred/chromium", "/fallback/google-chrome"}

    monkeypatch.setattr(config_module.os.path, "exists", exists)
    monkeypatch.setattr(config_module.os, "access", lambda path, mode: exists(path))
    assert config_module.find_chrome_executable() == "/preferred/chromium"


def test_fork_version_source_label():
    assert 'version = "0.50.3+AHB"' in Path("pyproject.toml").read_text(encoding="utf-8")
