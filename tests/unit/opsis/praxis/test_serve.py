"""Tests for opsis.praxis.serve — the live loop over http.client.

Subrule-level: one route each, exercised against a real bound server on a
seeded tmp workspace.
"""

from __future__ import annotations

import http.client
import threading

import pytest

from lexic.compile import compile_text
from opsis.opsis import render_scene
from opsis.opsis.scene import Ring, Space
from opsis.praxis.roots import thaw
from opsis.praxis.serve import scene_of, serve
from tests.paths import GROUND_TRUTH


@pytest.fixture
def running_server(tmp_path):
    """A bound server, serving in a daemon thread, seeded with one grammar."""
    (tmp_path / "resources" / "ground_truth").mkdir(parents=True)
    text = (GROUND_TRUTH / "list.gbnf").read_text(encoding="utf-8")
    (tmp_path / "resources" / "ground_truth" / "list.gbnf").write_text(
        text, encoding="utf-8"
    )
    server = serve(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()


def _request(server, method, path, body=None):
    conn = http.client.HTTPConnection(*server.server_address)
    try:
        conn.request(method, path, body=body)
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8")
    finally:
        conn.close()


def _request_with_headers(server, method, path, body=None):
    """Like ``_request``, but keeps the response headers for header-asserting tests."""
    conn = http.client.HTTPConnection(*server.server_address)
    try:
        conn.request(method, path, body=body)
        resp = conn.getresponse()
        headers = dict(resp.getheaders())
        return resp.status, headers, resp.read().decode("utf-8")
    finally:
        conn.close()


def test_get_root_serves_a_page(running_server):
    """GET / renders the opsis page for the (still empty) session."""
    status, body = _request(running_server, "GET", "/")
    assert status == 200
    assert "opsis" in body


def test_get_files_lists_the_seeded_grammar(running_server):
    """GET /files lists the workspace-relative seeded grammar."""
    status, body = _request(running_server, "GET", "/files")
    assert status == 200
    assert "resources/ground_truth/list.gbnf" in body.splitlines()


def test_open_then_root_shows_the_new_ring(running_server):
    """POST /open of the seeded grammar makes its rung 0 ring show up on /."""
    status, _ = _request(
        running_server, "POST", "/open", body="resources/ground_truth/list.gbnf"
    )
    assert status == 200

    _, page_body = _request(running_server, "GET", "/")
    assert "l0r0" in page_body


def test_rung_edit_returns_a_two_rung_summary(running_server):
    """POST /rung/0/1 with an instance text summarises both rungs."""
    _request(running_server, "POST", "/open", body="resources/ground_truth/list.gbnf")

    status, body = _request(running_server, "POST", "/rung/0/1", body="- item\n")

    assert status == 200
    assert "rung 0" in body
    assert "rung 1" in body


def test_open_escaping_the_workspace_refuses(running_server):
    """POST /open of a path outside the workspace refuses with 422."""
    status, _ = _request(running_server, "POST", "/open", body="../escape")
    assert status == 422


def test_root_carries_the_rung_0_editor_prefilled_with_the_grammar_text(
    running_server,
):
    """GET / carries rung 0's editor frame with the grammar text in a textarea."""
    _request(running_server, "POST", "/open", body="resources/ground_truth/list.gbnf")

    _, page_body = _request(running_server, "GET", "/")

    assert 'data-frame="ed-l0r0"' in page_body
    start = page_body.index('id="t-l0r0"')
    end = page_body.index("</textarea>", start)
    assert "item" in page_body[start:end]


def test_root_chips_row_is_not_off_for_a_gbnf_root(running_server):
    """A gbnf root can spell directive comments, so its chips row is not disabled."""
    _request(running_server, "POST", "/open", body="resources/ground_truth/list.gbnf")

    _, page_body = _request(running_server, "GET", "/")

    assert 'class="chips off"' not in page_body
    assert 'class="chips"' in page_body


def test_root_carries_a_fan_for_the_compiled_reading(running_server):
    """Rung 0's fan for the compiled reading carries a known rule's data-rule."""
    _request(running_server, "POST", "/open", body="resources/ground_truth/list.gbnf")
    # A single opened rung starts terminal (no compiled reading yet); growing
    # the ladder gives rung 0 its compiled reading, and its fan.
    _request(running_server, "POST", "/rung/0/1", body="- item\n")

    _, page_body = _request(running_server, "GET", "/")

    assert 'data-frame="fan-l0r0-rules"' in page_body
    assert 'data-rule="root"' in page_body


def test_root_carries_an_instance_fan_for_the_edited_rung(running_server):
    """Editing rung 1 with an instance text gives that rung its own instance fan."""
    _request(running_server, "POST", "/open", body="resources/ground_truth/list.gbnf")
    _request(running_server, "POST", "/rung/0/1", body="- item\n")

    _, page_body = _request(running_server, "GET", "/")

    assert 'data-frame="fan-l0r1-instance"' in page_body


def test_root_page_script_still_carries_the_deixis_listener(running_server):
    """The page's script keeps the one document-level deixis listener."""
    _, page_body = _request(running_server, "GET", "/")

    assert 'e.target.closest("[data-rule]")' in page_body


def test_notation_root_chips_row_is_off_with_its_reason(running_server, tmp_path):
    """A notation root carries no comments, so its chips row draws off with a reason."""
    grammar_text = (GROUND_TRUTH / "list.gbnf").read_text(encoding="utf-8")
    cg = compile_text(grammar_text)
    (tmp_path / "notation.txt").write_text(repr(cg.grammar), encoding="utf-8")

    status, _ = _request(running_server, "POST", "/open", body="notation.txt")
    assert status == 200

    _, page_body = _request(running_server, "GET", "/")
    assert 'class="chips off"' in page_body
    assert "carries no comments" in page_body


def test_export_writes_the_generated_module(running_server, tmp_path):
    """POST /export of a compiled rung writes generated/<stem>.py."""
    _request(running_server, "POST", "/open", body="resources/ground_truth/list.gbnf")
    # A single opened rung starts terminal (no compiled reading yet); growing
    # the ladder gives rung 0 its compiled reading to export.
    _request(running_server, "POST", "/rung/0/1", body="- item\n")

    status, body = _request(running_server, "POST", "/export", body="0/0")

    assert status == 200
    assert body.strip().startswith("generated/")
    assert (tmp_path / body.strip()).exists()


def test_get_session_is_the_acceptance_pin_for_freeze_thaw(running_server):
    """THE ACCEPTANCE PIN: GET /session freezes the scene; thaw(body) round-trips it byte-stably."""
    _request(running_server, "POST", "/open", body="resources/ground_truth/list.gbnf")
    _request(running_server, "POST", "/rung/0/1", body="- item\n")

    status, headers, body = _request_with_headers(running_server, "GET", "/session")

    assert status == 200
    assert headers["Content-Type"].startswith("text/plain")
    assert headers["Content-Disposition"] == 'attachment; filename="session.scene"'

    thawed = thaw(body)
    expected = scene_of(running_server.session)
    assert render_scene(thawed) == render_scene(expected)
    assert repr(thawed) == body


def test_open_session_file_ingresses_and_splices_the_thawed_rings(
    running_server, tmp_path
):
    """POST /open of a saved session file re-enters its rings on the next GET /."""
    scene = Space(Ring("l0r0"), Ring("extra"))
    (tmp_path / "x.scene").write_text(repr(scene), encoding="utf-8")

    _, before_body = _request(running_server, "GET", "/")
    before = before_body.count('class="nd ring')

    status, open_body = _request(running_server, "POST", "/open", body="x.scene")
    assert status == 200
    assert open_body.startswith("scene")

    _, after_body = _request(running_server, "GET", "/")
    after = after_body.count('class="nd ring')

    assert after > before


def test_get_root_carries_the_spawn_bar_picker_and_session_window(running_server):
    """GET / carries the spawn bar, the picker frame, and the session window."""
    _, page_body = _request(running_server, "GET", "/")

    assert 'id="spawnbar"' in page_body
    assert 'data-act="picker"' in page_body
    assert 'data-act="freeze"' in page_body
    assert 'data-act="session"' in page_body
    assert 'data-frame="picker"' in page_body
    assert 'id="session-notation"' in page_body
    assert "Space(" in page_body


def test_get_root_script_carries_the_frozen_guard_and_freeze_download(running_server):
    """The page script carries the FROZEN guard, the /files fetch, and the freeze download."""
    _, page_body = _request(running_server, "GET", "/")

    assert "FROZEN" in page_body
    assert "frozen" in page_body
    assert "/files" in page_body
    assert "freezeSnapshot" in page_body
    assert "opsis-frozen.html" in page_body


def test_get_session_on_an_empty_session_thaws_to_an_empty_space(running_server):
    """GET /session on a still-empty session returns a thawable, empty scene."""
    status, body = _request(running_server, "GET", "/session")

    assert status == 200
    assert len(thaw(body)) == 0
