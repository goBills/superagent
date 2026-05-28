import pytest
import requests

from superagent.data.probe_sportsdataio import probe_sportsdataio_access
from superagent.data.sportsdataio_client import SportsDataIOClient, SportsDataIOError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("boom", response=self)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "timeout": timeout})
        return self.response


def test_sportsdataio_client_sends_key_as_header_not_query_param():
    session = FakeSession(FakeResponse(payload=[{"Name": "Mike Evans", "Team": "SF"}]))
    client = SportsDataIOClient(api_key="abc123", session=session)

    payload = client.get_json("/scores/json/Players")

    assert payload[0]["Name"] == "Mike Evans"
    call = session.calls[0]
    assert "abc123" not in call["url"]
    assert call["headers"]["Ocp-Apim-Subscription-Key"] == "abc123"


def test_sportsdataio_client_requires_configured_key():
    with pytest.raises(SportsDataIOError, match="SPORTSDATAIO_API_KEY"):
        SportsDataIOClient(api_key="")


def test_sportsdataio_client_error_redacts_key():
    session = FakeSession(FakeResponse(status_code=403, text="Subscription Required"))
    client = SportsDataIOClient(api_key="secret-key-value", session=session)

    with pytest.raises(SportsDataIOError) as exc:
        client.get_json("/scores/json/Players")

    assert "Subscription Required" in str(exc.value)
    assert "secret-key-value" not in str(exc.value)


def test_probe_sportsdataio_access_summarizes_mocked_endpoints(monkeypatch):
    responses = {
        "/scores/json/Players": [{"Name": "Mike Evans", "Team": "SF", "Position": "WR"}],
        "/scores/json/Byes/2026": [{"Team": "SF", "ByeWeek": 14}],
        "/scores/json/DepthChartsAll": [{"Team": "SF", "DepthCharts": []}],
        "/projections/json/InjuredPlayers": [],
        "/projections/json/PlayerSeasonProjectionStats/2026": [
            {"Name": "Mike Evans", "AverageDraftPositionPPR": 40.2}
        ],
    }

    def fake_get_json(self, path, season=None):
        formatted = path.format(season=season) if season else path
        return responses[formatted]

    monkeypatch.setattr("superagent.data.probe_sportsdataio.SportsDataIOClient.__init__", lambda self: None)
    monkeypatch.setattr("superagent.data.probe_sportsdataio.SportsDataIOClient.get_json", fake_get_json)

    result = probe_sportsdataio_access(season=2026)

    assert result["summary"] == {"checked": 5, "accessible": 5, "blocked_or_failed": 0}
    players = next(endpoint for endpoint in result["endpoints"] if endpoint["name"] == "players")
    assert players["count"] == 1
    assert players["samples"][0]["Team"] == "SF"
