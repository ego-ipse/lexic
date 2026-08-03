"""The whole ladder over a real server — open, spawn, drop, edit, reflect.

Runs ``serve`` on an actual loopback socket (port 0) in a background thread,
the way a browser tab would drive it, and checks the invariant that made this
suite worth writing: a bad gesture answers with a refusal and the connection
stays alive, rather than the server going down or the page corrupting.
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path

import pytest

from lexic.model import GrammarModel
from opsis.praxis.reflect import REFLECTED
from opsis.praxis.serve import OpsisServer, serve

_VOID = frozenset(
    {"br", "input", "img", "hr", "meta", "link", "area", "base", "col", "wbr"}
)


class _TagChecker(HTMLParser):
    """Tracks an open-tag stack, flagging any mismatched or unclosed close."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.mismatches: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        """Push a real (non-void) element onto the open-tag stack."""
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        """A closing tag must match whatever is on top of the stack."""
        if not self.stack or self.stack[-1] != tag:
            self.mismatches.append((tag, list(self.stack)))
        else:
            self.stack.pop()


@pytest.fixture(name="server")
def _server() -> Iterator[OpsisServer]:
    """A live opsis server over the repo workspace, on an ephemeral port."""
    instance = serve(Path.cwd(), 0)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        thread.join(timeout=5)


def _base(server: OpsisServer) -> str:
    """The server's own loopback URL."""
    return f"http://127.0.0.1:{server.server_address[1]}"


def _post(server: OpsisServer, path: str, body: str = "") -> tuple[int, str]:
    """POST one gesture; refusals come back as a status and a message, never a raise."""
    request = urllib.request.Request(
        _base(server) + path, data=body.encode("utf-8"), method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _get(server: OpsisServer, path: str) -> tuple[int, str]:
    """GET one page or fragment."""
    with urllib.request.urlopen(_base(server) + path, timeout=10) as response:
        return response.status, response.read().decode("utf-8")


def test_open_spawn_drop_edit_round_trips_a_model(server: OpsisServer) -> None:
    """Opening a grammar, spawning a text, dropping the grammar on it, and
    editing it produces a model whose ``to_text()`` reproduces the input."""
    status, _ = _post(server, "/open", "resources/ground_truth/json.gbnf")
    assert status == 200
    session = server.session
    grammar = next(r for r in session.readings.values() if r.title == "json.gbnf")
    assert grammar.compiled is not None

    status, _ = _post(server, "/new", "text")
    assert status == 200
    spawned = next(r for r in session.readings.values() if r.title == "new text")

    status, _ = _post(server, f"/drop/{grammar.ident}/{spawned.ident}")
    assert status == 200
    assert session.readings[spawned.ident].reader == grammar.ident

    text = '{"a":[1,true]}'
    status, _ = _post(server, f"/text/{spawned.ident}", text)
    assert status == 200
    product = session.readings[spawned.ident].product
    assert session.readings[spawned.ident].error == ""
    assert isinstance(product, GrammarModel)
    assert product.to_text() == text


@pytest.mark.parametrize(
    "method_path_body",
    [
        ("POST", "/drop/nope/nope", ""),
        ("POST", "/unplug/zzz", ""),
        ("POST", "/remove/zzz", ""),
        ("POST", "/do/zzz/twin", ""),
        ("POST", "/text/zzz", "hi"),
        ("POST", "/thaw", "not a session"),
        ("POST", "/new", "nonsense"),
    ],
)
def test_every_bad_gesture_refuses_without_taking_the_server_down(
    server: OpsisServer, method_path_body: tuple[str, str, str]
) -> None:
    """A gesture naming a reading that is not there answers 4xx/5xx, and the
    server is still serving requests afterward."""
    _, path, body = method_path_body
    status, message = _post(server, path, body)
    assert status >= 400
    assert message

    status, _ = _get(server, "/world")
    assert status == 200


def test_root_page_is_well_formed_html(server: OpsisServer) -> None:
    """GET / has no unclosed or mismatched tags.

    A void element carries no closing tag, which is a fact about the
    tag rather than something every call site remembers — so this holds
    for whatever the page grows next, not just for what it has now.
    """
    status, body = _get(server, "/")
    assert status == 200
    checker = _TagChecker()
    checker.feed(body)
    assert not checker.mismatches
    assert not checker.stack


def test_reflective_rung_edits_the_world_through_its_own_scene(
    server: OpsisServer,
) -> None:
    """Editing the reflected scene's text changes what ``/world`` draws."""
    status, _ = _post(server, "/open", "resources/ground_truth/json.gbnf")
    assert status == 200
    session = server.session

    status, _ = _post(server, "/reflect")
    assert status == 200
    scene = next(r for r in session.readings.values() if r.kind == REFLECTED)
    assert "abnf.flavour.ir" in scene.text

    retitled = scene.text.replace("abnf.flavour.ir", "RETITLED-BY-TEST")
    status, _ = _post(server, f"/text/{scene.ident}", retitled)
    assert status == 200

    status, world = _get(server, "/world")
    assert status == 200
    assert "RETITLED-BY-TEST" in world
