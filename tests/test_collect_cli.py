import json
from pathlib import Path

import httpx

from scripts import collect
from tests.fakes import HashingEmbedder

FIXTURES = Path(__file__).parent / "collectors" / "fixtures"


def test_cli_runs_collector_with_mock_transport(capsys):
    payload = json.loads((FIXTURES / "remotive.json").read_text(encoding="utf-8"))
    mock_transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    client_class = httpx.Client

    assert collect.main(
        ["--source", "remotive", "--limit", "1"],
        database_url="sqlite:///:memory:",
        client_factory=lambda: client_class(transport=mock_transport),
        embedder_factory=HashingEmbedder,
    ) == 0
    output = capsys.readouterr().out
    assert "fetched=1" in output
    assert "new=1" in output
