from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_one(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old!r}")
    write(path, text.replace(old, new, 1))


def replace_n(path: str, old: str, new: str, expected: int) -> None:
    text = read(path)
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} matches, found {count}: {old!r}")
    write(path, text.replace(old, new))


def patch_pyproject() -> None:
    replace_one("pyproject.toml", 'version = "0.50.3"', 'version = "0.50.3+AHB"')
    replace_one(
        "pyproject.toml",
        '    "Programming Language :: Python :: 3.13",\n',
        '    "Programming Language :: Python :: 3.13",\n    "Programming Language :: Python :: 3.14",\n',
    )


def patch_generator() -> None:
    path = "generate_cdp.py"
    replace_one(path, "with json_path.open() as json_file:", 'with json_path.open(encoding="utf-8") as json_file:')
    replace_one(path, 'with init_path.open("w") as init_file:', 'with init_path.open("w", encoding="utf-8", newline="\\n") as init_file:')
    replace_one(path, 'with doc.open("w") as f:', 'with doc.open("w", encoding="utf-8", newline="\\n") as f:')
    replace_one(path, 'with module_path.open("w") as module_file:\n                module_file.write(domain.generate_code())', 'with module_path.open("w", encoding="utf-8", newline="\\n") as module_file:\n                module_file.write(apply_generated_compatibility_fixes(domain, domain.generate_code()))')
    replace_one(path, '(output_path / "README.md").write_text(GENERATED_PACKAGE_NOTICE)', '(output_path / "README.md").write_text(GENERATED_PACKAGE_NOTICE, encoding="utf-8")')
    replace_one(path, 'util_path.write_text(\n            dedent(', 'util_path.write_text(\n            dedent(')
    # Add encoding to the util write_text call without changing the generated body.
    text = read(path)
    needle = '            )\n        )\n\n    finally:\n'
    replacement = '            ),\n            encoding="utf-8",\n        )\n\n    finally:\n'
    if needle not in text:
        raise RuntimeError("generate_cdp.py: util write_text terminator not found")
    write(path, text.replace(needle, replacement, 1))

    text = read(path)
    anchor = '\n\ndef selfgen():\n'
    if text.count(anchor) != 1:
        raise RuntimeError("generate_cdp.py: selfgen anchor not unique")
    helper = '''\n\ndef apply_generated_compatibility_fixes(domain, code: str) -> str:\n    """Preserve local compatibility hardening across CDP regeneration."""\n    if domain.domain != "Network":\n        return code\n\n    replacements = {\n        "priority=CookiePriority.from_json(json['priority']),":\n            "priority=CookiePriority.from_json(json.get('priority', 'Medium')),",\n        "source_scheme=CookieSourceScheme.from_json(json['sourceScheme']),":\n            "source_scheme=CookieSourceScheme.from_json(json.get('sourceScheme', 'Unset')),",\n        "source_port=int(json['sourcePort']),":\n            "source_port=int(json.get('sourcePort', -1)),",\n    }\n    for old, new in replacements.items():\n        if old not in code:\n            raise RuntimeError(f"expected Network.Cookie generator fragment missing: {old}")\n        code = code.replace(old, new, 1)\n    return code\n'''
    write(path, text.replace(anchor, helper + anchor, 1))


def patch_network_encoding_and_cookie_parser() -> None:
    path = ROOT / "nodriver/cdp/network.py"
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    if "JSON (±Inf)." not in text:
        raise RuntimeError("network.py: expected ±Inf documentation marker not found")
    replacements = {
        "priority=CookiePriority.from_json(json['priority']),":
            "priority=CookiePriority.from_json(json.get('priority', 'Medium')),",
        "source_scheme=CookieSourceScheme.from_json(json['sourceScheme']),":
            "source_scheme=CookieSourceScheme.from_json(json.get('sourceScheme', 'Unset')),",
        "source_port=int(json['sourcePort']),":
            "source_port=int(json.get('sourcePort', -1)),",
    }
    for old, new in replacements.items():
        if text.count(old) != 1:
            raise RuntimeError(f"network.py: expected one cookie-parser fragment: {old}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    # Prove the committed source is strict UTF-8, not merely displayable by GitHub.
    path.read_bytes().decode("utf-8")


def patch_connection_serialization() -> None:
    path = "nodriver/core/connection.py"
    old = '''        method, *params = next(cdp_obj).values()\n        if params:\n            params = params.pop()\n        _id = next(self.__count__)\n        message = {"method": method, "params": params, "id": _id}\n'''
    new = '''        command = next(cdp_obj)\n        method = command["method"]\n        params = command.get("params") or {}\n        if not isinstance(params, dict):\n            raise TypeError(f"CDP command params must be a dict, got {type(params).__name__}")\n        _id = next(self.__count__)\n        message = {"method": method, "params": params, "id": _id}\n'''
    replace_one(path, old, new)


def patch_permissions() -> None:
    path = "nodriver/core/browser.py"
    old = '''        permissions = list(cdp.browser.PermissionType)\n        permissions.remove(cdp.browser.PermissionType.FLASH)\n        permissions.remove(cdp.browser.PermissionType.CAPTURED_SURFACE_CONTROL)\n        await self.send(cdp.browser.grant_permissions(permissions))\n'''
    new = '''        excluded_permission_names = {"FLASH", "CAPTURED_SURFACE_CONTROL"}\n        permissions = [\n            permission\n            for permission in cdp.browser.PermissionType\n            if permission.name not in excluded_permission_names\n        ]\n        await self.send(cdp.browser.grant_permissions(permissions))\n'''
    replace_one(path, old, new)


def patch_tab_falsey_values_and_scroll() -> None:
    path = "nodriver/core/tab.py"
    replace_n(path, "if remote_object.value:\n", "if remote_object.value is not None:\n", expected=2)
    old = '''        res = await self.evaluate(\n            "document.body.offsetHeight - window.innerHeight == window.scrollY"\n        )\n        if res:\n            return res[0].value\n'''
    new = '''        return bool(\n            await self.evaluate(\n                "document.body.offsetHeight - window.innerHeight == window.scrollY",\n                return_by_value=True,\n            )\n        )\n'''
    replace_one(path, old, new)


def patch_mouse_drag() -> None:
    path = "nodriver/core/element.py"
    old = '''        end_point = None\n        if isinstance(destination, Element):\n            try:\n                end_point = (await destination.get_position()).center\n            except AttributeError:\n                return\n            if not end_point:\n                logger.warning("could not calculate box model for %s", destination)\n                return\n        elif isinstance(destination, (tuple, list)):\n            if relative:\n                end_point = (\n                    start_point[0] + destination[0],\n                    start_point[1] + destination[1],\n                )\n            else:\n                end_point = destination\n        await self._tab.mouse_drag(\n            start_point, end_point, relative=relative, steps=steps\n        )\n'''
    new = '''        end_point = None\n        relative_move = relative\n        if isinstance(destination, Element):\n            try:\n                end_point = (await destination.get_position()).center\n            except AttributeError:\n                return\n            if not end_point:\n                logger.warning("could not calculate box model for %s", destination)\n                return\n            # Element destinations are already absolute coordinates.\n            relative_move = False\n        elif isinstance(destination, (tuple, list)):\n            # Tab.mouse_drag is the single owner of relative-coordinate expansion.\n            end_point = destination\n        await self._tab.mouse_drag(\n            start_point, end_point, relative=relative_move, steps=steps\n        )\n'''
    replace_one(path, old, new)


def patch_path_order() -> None:
    path = "nodriver/core/config.py"
    old = '''    winner = None\n\n    if return_all and rv:\n        return rv\n\n    if rv and len(rv) > 1:\n        # assuming the shortest path wins\n        winner = min(rv, key=lambda x: len(x))\n\n    elif len(rv) == 1:\n        winner = rv[0]\n\n    if winner:\n        return os.path.normpath(winner)\n\n    raise FileNotFoundError(\n'''
    new = '''    if return_all and rv:\n        return rv\n\n    if rv:\n        # PATH is ordered by precedence; honor the first executable discovered.\n        return os.path.normpath(rv[0])\n\n    raise FileNotFoundError(\n'''
    replace_one(path, old, new)


def patch_tox() -> None:
    replace_one("tox.ini", "envlist = py{37,38,39,310,311}", "envlist = py{39,310,311,312,313,314}")


def add_tests() -> None:
    tests = ROOT / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_ahb_fork_compat.py").write_text(
        '''from __future__ import annotations\n\nimport asyncio\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nimport pytest\n\nimport nodriver\nfrom nodriver import cdp\nfrom nodriver.core import config as config_module\nfrom nodriver.core.element import Element\nfrom nodriver.core.tab import Tab\n\n\ndef test_python_314_generated_sources_are_utf8():\n    for path in Path("nodriver/cdp").glob("*.py"):\n        path.read_bytes().decode("utf-8")\n\n\ndef test_cookie_parser_tolerates_recent_chrome_omissions():\n    cookie = cdp.network.Cookie.from_json(\n        {\n            "name": "cf_clearance",\n            "value": "token",\n            "domain": ".example.test",\n            "path": "/",\n            "size": 5,\n            "httpOnly": True,\n            "secure": True,\n            "session": False,\n        }\n    )\n    assert cookie.priority is cdp.network.CookiePriority.MEDIUM\n    assert cookie.source_scheme is cdp.network.CookieSourceScheme.UNSET\n    assert cookie.source_port == -1\n\n\ndef test_grant_all_permissions_does_not_require_removed_flash_enum():\n    assert not hasattr(cdp.browser.PermissionType, "FLASH")\n    excluded = {"FLASH", "CAPTURED_SURFACE_CONTROL"}\n    permissions = [p for p in cdp.browser.PermissionType if p.name not in excluded]\n    assert permissions\n    assert all(p.name not in excluded for p in permissions)\n\n\ndef test_scroll_bottom_reached_accepts_boolean_evaluate_result():\n    tab = object.__new__(Tab)\n\n    async def evaluate(*args, **kwargs):\n        assert kwargs["return_by_value"] is True\n        return True\n\n    tab.evaluate = evaluate\n    assert asyncio.run(Tab.scroll_bottom_reached(tab)) is True\n\n\ndef test_element_relative_mouse_drag_is_expanded_once():\n    calls = []\n\n    class FakeTab:\n        async def mouse_drag(self, source, dest, relative=False, steps=1):\n            calls.append((source, dest, relative, steps))\n\n    class FakeElement(Element):\n        def __init__(self, tab, center):\n            self._tab = tab\n            self._center = center\n\n        async def get_position(self):\n            return SimpleNamespace(center=self._center)\n\n    element = FakeElement(FakeTab(), (100, 200))\n    asyncio.run(element.mouse_drag((10, -5), relative=True, steps=3))\n    assert calls == [((100, 200), (10, -5), True, 3)]\n\n\ndef test_element_destination_forces_absolute_drag():\n    calls = []\n\n    class FakeTab:\n        async def mouse_drag(self, source, dest, relative=False, steps=1):\n            calls.append((source, dest, relative, steps))\n\n    class FakeElement(Element):\n        def __init__(self, tab, center):\n            self._tab = tab\n            self._center = center\n\n        async def get_position(self):\n            return SimpleNamespace(center=self._center)\n\n    tab = FakeTab()\n    source = FakeElement(tab, (100, 200))\n    destination = FakeElement(tab, (300, 400))\n    asyncio.run(source.mouse_drag(destination, relative=True))\n    assert calls == [((100, 200), (300, 400), False, 1)]\n\n\ndef test_find_chrome_executable_honors_path_order(monkeypatch):\n    monkeypatch.setattr(config_module, "is_posix", True)\n    monkeypatch.setenv("PATH", "/preferred:/fallback")\n\n    def exists(path):\n        return path in {"/preferred/chromium", "/fallback/google-chrome"}\n\n    monkeypatch.setattr(config_module.os.path, "exists", exists)\n    monkeypatch.setattr(config_module.os, "access", lambda path, mode: exists(path))\n    assert config_module.find_chrome_executable() == "/preferred/chromium"\n\n\ndef test_fork_version_source_label():\n    assert 'version = "0.50.3+AHB"' in Path("pyproject.toml").read_text(encoding="utf-8")\n''',
        encoding="utf-8",
        newline="\n",
    )


def add_qualification_workflow() -> None:
    workflows = ROOT / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / "ahb-python314-qualification.yml").write_text(
        '''name: AHB Python 3.14 Qualification\n\non:\n  push:\n    branches: ["compat/python-314-ahb"]\n  pull_request:\n  workflow_dispatch:\n\npermissions:\n  contents: read\n\njobs:\n  python314:\n    runs-on: ubuntu-latest\n    timeout-minutes: 20\n    steps:\n      - uses: actions/checkout@v5\n      - uses: actions/setup-python@v6\n        with:\n          python-version: "3.14"\n          cache: pip\n      - name: Install qualification tools\n        run: python -m pip install --upgrade pip build 'pytest>=9.0.3' pip-audit\n      - name: Prove generated sources compile under Python 3.14\n        run: python -m compileall -q nodriver\n      - name: Install fork\n        run: python -m pip install -e .\n      - name: Dependency consistency\n        run: python -m pip check\n      - name: Regression suite\n        run: python -m pytest -q tests/test_ahb_fork_compat.py\n      - name: Import and API contract\n        run: |\n          python - <<'PY'\n          import inspect\n          import nodriver as uc\n          from nodriver import cdp\n          from nodriver.core.browser import Browser\n          assert callable(uc.start)\n          assert hasattr(cdp.network, "RequestWillBeSent")\n          assert hasattr(cdp.network, "ResponseReceived")\n          assert "proxy_server" in inspect.signature(Browser.create_context).parameters\n          print("NODRIVER_AHB_PYTHON314_IMPORT=PASS")\n          PY\n      - name: Dependency audit\n        run: python -m pip_audit\n      - name: Build wheel and print exact SHA-256\n        run: |\n          rm -rf dist build\n          python -m build --wheel\n          python - <<'PY'\n          import hashlib\n          import pathlib\n          wheels = list(pathlib.Path("dist").glob("*.whl"))\n          assert len(wheels) == 1, wheels\n          wheel = wheels[0]\n          digest = hashlib.sha256(wheel.read_bytes()).hexdigest()\n          print(f"NODRIVER_AHB_WHEEL={wheel.name}")\n          print(f"NODRIVER_AHB_WHEEL_SHA256={digest}")\n          PY\n''',
        encoding="utf-8",
        newline="\n",
    )


def add_provenance() -> None:
    (ROOT / "AHB_FORK_PROVENANCE.md").write_text(
        '''# AHB nodriver fork provenance\n\nThis branch is an AHB compatibility build derived from upstream nodriver 0.50.3.\n\nBuild label: `0.50.3+AHB` (PEP 440 tooling may normalize the local label to `0.50.3+ahb`).\n\nInitial upstream base: `a71cda374651d13815a42c5eeb61af04a711eaa7`.\n\nLocal compatibility scope:\n\n- strict UTF-8 generated CDP source for CPython 3.14;\n- empty CDP command parameters serialized as `{}`;\n- resilient Network.Cookie parsing for fields omitted by newer Chromium versions;\n- removed-permission-safe `grant_all_permissions()`;\n- falsey JavaScript value handling and `scroll_bottom_reached()`;\n- single-owner relative mouse-drag coordinate expansion;\n- POSIX PATH-order browser discovery;\n- Python 3.14 regression and wheel-digest qualification.\n\nAHB consumers must pin an exact commit. A wheel SHA-256 is accepted only from an exact-head successful qualification run.\n''',
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    patch_pyproject()
    patch_generator()
    patch_network_encoding_and_cookie_parser()
    patch_connection_serialization()
    patch_permissions()
    patch_tab_falsey_values_and_scroll()
    patch_mouse_drag()
    patch_path_order()
    patch_tox()
    add_tests()
    add_qualification_workflow()
    add_provenance()
    print("AHB_NODRIVER_FORK_PATCHES=APPLIED")


if __name__ == "__main__":
    main()
