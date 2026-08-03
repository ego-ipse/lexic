"""Tests for opsis.praxis.serve — the live loop over http.client.

Subrule-level: one route each, exercised against a real bound server on a
seeded tmp workspace.
"""

from __future__ import annotations

import http.client
import threading

import pytest

from opsis.praxis.serve import serve
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
