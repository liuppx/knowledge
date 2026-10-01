from __future__ import annotations

from fastapi.testclient import TestClient

from knowledge.api import routes_console
from knowledge.main import app

HTML = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
JSON = {"Accept": "application/json"}


def _fake_dist(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>spa-shell</body></html>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(routes_console, "web_dist_dir", dist)
    monkeypatch.setattr(routes_console, "web_index", dist / "index.html")
    return dist


def test_deep_links_serve_spa_shell_for_browsers(tmp_path, monkeypatch):
    _fake_dist(tmp_path, monkeypatch)
    client = TestClient(app)

    for path in ("/", "/kbs/1/search", "/warehouse", "/ops"):
        response = client.get(path, headers=HTML)
        assert response.status_code == 200, path
        assert "spa-shell" in response.text


def test_api_routes_and_json_clients_are_unaffected(tmp_path, monkeypatch):
    _fake_dist(tmp_path, monkeypatch)
    client = TestClient(app)

    # A real API route still wins over the catch-all (auth guard answers, not HTML).
    api = client.get("/kbs/1", headers=JSON)
    assert api.status_code in (401, 403)
    assert api.headers["content-type"].startswith("application/json")
    # Unknown path + JSON client -> plain 404, never the SPA shell.
    missing = client.get("/kbs/1/does-not-exist", headers=JSON)
    assert missing.status_code == 404
    assert "spa-shell" not in missing.text
    # Unknown non-GET paths stay 404 (not 405) so removed-API probes keep working.
    assert client.post("/retrieval/search", json={"query": "q"}).status_code == 404
    assert client.delete("/warehouse/auth/binding").status_code == 404
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200


def test_dist_root_files_and_traversal(tmp_path, monkeypatch):
    dist = _fake_dist(tmp_path, monkeypatch)
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    client = TestClient(app)

    assert client.get("/favicon.svg").text == "<svg/>"
    escaped = client.get("/../secret.txt", headers=JSON)
    assert escaped.status_code == 404
    assert "nope" not in escaped.text
    assert dist.is_dir()


def test_without_dist_legacy_console_and_404(tmp_path, monkeypatch):
    monkeypatch.setattr(routes_console, "web_dist_dir", tmp_path / "absent")
    monkeypatch.setattr(routes_console, "web_index", tmp_path / "absent" / "index.html")
    client = TestClient(app)

    assert client.get("/kbs/1/search", headers=HTML).status_code == 404
    legacy = client.get("/", headers=HTML)
    assert legacy.status_code == 200
    assert "spa-shell" not in legacy.text
