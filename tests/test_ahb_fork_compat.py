from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import nodriver
from nodriver import cdp
from nodriver.core import config as config_module
from nodriver.core import util as util_module
from nodriver.core.browser import Browser, _wait_for_devtools
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


def test_browser_startup_readiness_allows_more_than_five_probes():
    class FakeHTTP:
        def __init__(self):
            self.calls = 0

        async def get(self, endpoint):
            assert endpoint == "version"
            self.calls += 1
            if self.calls <= 6:
                raise ConnectionRefusedError("not ready")
            return {"webSocketDebuggerUrl": "ws://127.0.0.1/devtools/browser/test"}

    http = FakeHTTP()
    info = asyncio.run(_wait_for_devtools(http, timeout=1.0, poll_interval=0))
    assert http.calls == 7
    assert info["webSocketDebuggerUrl"].startswith("ws://")


def test_browser_startup_readiness_fails_early_when_child_exits():
    class FakeHTTP:
        async def get(self, endpoint):
            raise AssertionError("DevTools must not be probed after browser exit")

    with pytest.raises(RuntimeError, match="return code 17"):
        asyncio.run(
            _wait_for_devtools(
                FakeHTTP(),
                process=SimpleNamespace(returncode=17),
                timeout=1.0,
                poll_interval=0,
            )
        )


def test_browser_startup_readiness_honors_deadline():
    class SlowHTTP:
        async def get(self, endpoint):
            await asyncio.sleep(60)

    with pytest.raises(TimeoutError, match="not ready within"):
        asyncio.run(_wait_for_devtools(SlowHTTP(), timeout=0.01, poll_interval=0))


def test_browser_aclose_closes_child_connections_and_reaps_process():
    events = []

    class FakeChild:
        async def aclose(self):
            events.append("child-close")

    class FakeProcess:
        def __init__(self):
            self.returncode = None
            self.pid = 4242
            self.terminated = False
            self.killed = False
            self.communicated = False

        def terminate(self):
            self.terminated = True
            self.returncode = -15
            events.append("terminate")

        def kill(self):
            self.killed = True
            self.returncode = -9
            events.append("kill")

        async def communicate(self):
            self.communicated = True
            events.append("communicate")
            return b"", b""

    async def exercise():
        browser = object.__new__(Browser)
        browser._targets = [FakeChild(), FakeChild()]
        browser._mapper = {}
        browser._listener_task = None
        browser.socket = None
        process = FakeProcess()
        browser._process = process
        browser._process_pid = process.pid
        util_module.get_registered_instances().add(browser)

        await browser.aclose()

        assert browser._targets == []
        assert browser._process is None
        assert browser._process_pid is None
        assert browser not in util_module.get_registered_instances()
        return process

    process = asyncio.run(exercise())
    assert events[:2] == ["child-close", "child-close"]
    assert process.terminated is True
    assert process.communicated is True
    assert process.killed is False



def test_target_destroy_closes_child_before_eviction():
    events = []

    class FakeChild:
        def __init__(self):
            self.target = SimpleNamespace(target_id=cdp.target.TargetID("child"))

        async def aclose(self):
            events.append("close")

    async def exercise():
        parent = object.__new__(Browser)
        parent.target = SimpleNamespace(target_id=cdp.target.TargetID("browser"))
        child = FakeChild()
        parent._targets = [child]

        await parent._attach_handler(
            cdp.target.TargetDestroyed(target_id=cdp.target.TargetID("child"))
        )

        assert parent._targets == []

    asyncio.run(exercise())
    assert events == ["close"]


def test_update_targets_closes_stale_child_before_eviction():
    events = []

    class FakeChild:
        def __init__(self):
            self.target = SimpleNamespace(target_id=cdp.target.TargetID("stale"))

        async def aclose(self):
            events.append("close")

    async def exercise():
        browser = object.__new__(Browser)
        child = FakeChild()
        browser._targets = [child]

        async def send(_):
            return []

        browser.send = send
        await Browser.update_targets(browser)
        assert browser._targets == []

    asyncio.run(exercise())
    assert events == ["close"]


def test_fork_version_source_label():
    assert 'version = "0.50.3+AHB"' in Path("pyproject.toml").read_text(encoding="utf-8")
