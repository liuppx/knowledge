from knowledge import cli


def test_knowledge_cli_defaults_to_local_development_server(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    cli.main([])

    assert calls == [
        (("knowledge.main:app",), {"host": "127.0.0.1", "port": 8002, "reload": True})
    ]


def test_knowledge_cli_allows_custom_bind_and_disabling_reload(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    cli.main(["--host", "0.0.0.0", "--port", "9000", "--no-reload"])

    assert calls == [
        (("knowledge.main:app",), {"host": "0.0.0.0", "port": 9000, "reload": False})
    ]
