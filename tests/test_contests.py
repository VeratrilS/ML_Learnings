"""Tests for api.domain.contests — all HTTP is mocked, no network."""
from unittest import mock

import pytest
import requests
from flask import Flask

from api.domain import contests
from api.domain.contests import contests_bp

NOW = 1_800_000_000  # fixed "now" (epoch seconds)
DAY = 86400


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def cf_payload():
    return {"status": "OK", "result": [
        {"id": 3, "name": "CF Round C", "phase": "BEFORE", "startTimeSeconds": NOW + 2 * DAY, "durationSeconds": 7200},
        {"id": 2, "name": "CF Running", "phase": "CODING", "startTimeSeconds": NOW - 1800, "durationSeconds": 7200},
        {"id": 1, "name": "CF Finished", "phase": "FINISHED", "startTimeSeconds": NOW - 10 * DAY, "durationSeconds": 7200},
        {"id": 4, "name": "CF Far Future", "phase": "BEFORE", "startTimeSeconds": NOW + 45 * DAY, "durationSeconds": 7200},
        {"id": 5, "name": "CF No Start", "phase": "BEFORE", "durationSeconds": 7200},
    ]}


def lc_payload():
    weekly = {"title": "Weekly Contest 500", "titleSlug": "weekly-contest-500", "startTime": NOW + DAY, "duration": 5400}
    biweekly = {"title": "Biweekly Contest 190", "titleSlug": "biweekly-contest-190", "startTime": NOW + 3 * DAY, "duration": 5400}
    return {"data": {"upcomingContests": [weekly], "topTwoContests": [weekly, biweekly]}}


@pytest.fixture(autouse=True)
def _clean_cache():
    contests.clear_cache()
    yield
    contests.clear_cache()


@pytest.fixture
def http():
    """Patch requests.get (Codeforces) and requests.post (LeetCode) inside the contests module."""
    with mock.patch.object(contests.requests, "get") as g, mock.patch.object(contests.requests, "post") as p:
        g.return_value = FakeResp(cf_payload())
        p.return_value = FakeResp(lc_payload())
        yield g, p


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(contests_bp)
    return app.test_client()


def test_merges_filters_and_sorts(http):
    res = contests.get_contests(now=NOW)
    assert res["status"] == "success"
    assert res["errors"] == []
    names = [c["name"] for c in res["data"]]
    # running first, then by start; finished / >30 days / no-start dropped; LC weekly de-duplicated
    assert names == ["CF Running", "Weekly Contest 500", "CF Round C", "Biweekly Contest 190"]
    assert [c["running"] for c in res["data"]] == [True, False, False, False]


def test_contest_shape_and_urls(http):
    data = contests.get_contests(now=NOW)["data"]
    cf = next(c for c in data if c["name"] == "CF Round C")
    assert cf["platform"] == "codeforces"
    assert cf["url"] == "https://codeforces.com/contests/3"
    assert cf["register_url"] == "https://codeforces.com/contestRegistration/3"
    assert cf["duration_seconds"] == 7200
    assert cf["start"].endswith("Z") or cf["start"].endswith("+00:00")
    assert "start_ts" not in cf

    lc = next(c for c in data if c["platform"] == "leetcode")
    assert lc["url"] == "https://leetcode.com/contest/weekly-contest-500/"
    assert lc["start"] == "2027-01-16T08:00:00Z"  # NOW + 1 day
    assert lc["duration_seconds"] == 5400


def test_requests_use_timeouts_and_headers(http):
    g, p = http
    contests.get_contests(now=NOW)
    assert g.call_args.kwargs["timeout"] == 10
    assert p.call_args.kwargs["timeout"] == 10
    headers = p.call_args.kwargs["headers"]
    assert headers["Referer"] == "https://leetcode.com"
    assert headers["Content-Type"] == "application/json"
    assert "upcomingContests" in p.call_args.kwargs["json"]["query"]


def test_cache_reused_within_30_minutes(http):
    g, p = http
    contests.get_contests(now=NOW)
    contests.get_contests(now=NOW + 29 * 60)
    assert g.call_count == 1 and p.call_count == 1
    contests.get_contests(now=NOW + 31 * 60)
    assert g.call_count == 2 and p.call_count == 2


def test_cached_data_is_refiltered_by_current_time(http):
    contests.get_contests(now=NOW)
    later = contests.get_contests(now=NOW + 6000)  # CF Running (ends NOW+5400) has now ended
    assert "CF Running" not in [c["name"] for c in later["data"]]


def test_force_refresh_bypasses_cache(http):
    g, _ = http
    contests.get_contests(now=NOW)
    contests.get_contests(now=NOW + 60, force=True)
    assert g.call_count == 2


def test_leetcode_failure_still_returns_codeforces(http):
    _, p = http
    p.side_effect = requests.ConnectionError("boom")
    res = contests.get_contests(now=NOW)
    assert {c["platform"] for c in res["data"]} == {"codeforces"}
    assert len(res["errors"]) == 1 and "LeetCode" in res["errors"][0]


def test_codeforces_failure_still_returns_leetcode(http):
    g, _ = http
    g.return_value = FakeResp({"status": "FAILED", "comment": "Call limit exceeded"})
    res = contests.get_contests(now=NOW)
    assert {c["platform"] for c in res["data"]} == {"leetcode"}
    assert len(res["errors"]) == 1 and "Codeforces" in res["errors"][0]


def test_http_error_status_is_reported(http):
    g, _ = http
    g.return_value = FakeResp({}, status=503)
    res = contests.get_contests(now=NOW)
    assert any("Codeforces" in e for e in res["errors"])
    assert res["data"]


def test_partial_failure_retries_sooner(http):
    g, p = http
    p.side_effect = requests.Timeout()
    contests.get_contests(now=NOW)
    contests.get_contests(now=NOW + 60)
    assert p.call_count == 1  # still cached briefly
    p.side_effect = None
    res = contests.get_contests(now=NOW + 3 * 60)
    assert p.call_count == 2
    assert res["errors"] == []
    assert any(c["platform"] == "leetcode" for c in res["data"])


def test_total_failure_not_cached(http):
    g, p = http
    g.side_effect = requests.ConnectionError()
    p.side_effect = requests.ConnectionError()
    res = contests.get_contests(now=NOW)
    assert res["data"] == [] and len(res["errors"]) == 2
    contests.get_contests(now=NOW + 1)
    assert g.call_count == 2


def test_endpoint(http, client):
    with mock.patch.object(contests.time, "time", return_value=NOW):
        r = client.get("/api/contests")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "success"
    assert len(body["data"]) == 4
    assert body["errors"] == []
    assert client.get("/api/contests/").status_code == 200

