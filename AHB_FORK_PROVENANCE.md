# AHB nodriver fork provenance

This branch is an AHB compatibility build derived from upstream nodriver 0.50.3.

Build label: `0.50.3+AHB` (PEP 440 tooling may normalize the local label to `0.50.3+ahb`).

Initial upstream base: `a71cda374651d13815a42c5eeb61af04a711eaa7`.

Local compatibility scope:

- strict UTF-8 generated CDP source for CPython 3.14;
- empty CDP command parameters serialized as `{}`;
- resilient Network.Cookie parsing for fields omitted by newer Chromium versions;
- removed-permission-safe `grant_all_permissions()`;
- falsey JavaScript value handling and `scroll_bottom_reached()`;
- single-owner relative mouse-drag coordinate expansion;
- POSIX PATH-order browser discovery;
- bounded DevTools startup readiness with early browser-exit detection;
- complete async browser shutdown that closes child CDP websockets before event-loop teardown and reaps the Chromium subprocess;
- Python 3.14 regression and wheel-digest qualification.

AHB consumers must pin an exact commit. A wheel SHA-256 is accepted only from an exact-head successful qualification run.
