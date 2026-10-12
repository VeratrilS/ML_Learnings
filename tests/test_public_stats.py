import pytest

from api.app import app
from api.domain import public_stats as ps

LC = {"total": 500, "easy": 200, "medium": 250, "hard": 50, "contest_rating": 1850,
      "contests_attended": 20, "top_percentage": 7.5, "badges": 3}
CF = {"handle": "Raghavan_CP", "rating": 1600, "max_rating": 1700, "rank": "expert", "max_rank": "expert"}


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class Fetchers:
    """Stand-ins for the network calls; count calls and fail on demand."""
    def __init__(self):
        self.calls = 0
        self.fail_lc = set()
        self.fail_cf = False
        self.lc_total = 500

    def leetcode(self, username):
        self.calls += 1
        if username in self.fail_lc:
            raise RuntimeError("leetcode down")
        return dict(LC, total=self.lc_total)

    def codeforces(self, handle):
        self.calls += 1
        if self.fail_cf:
            raise RuntimeError("codeforces down")
        return dict(CF, handle=handle)

    def fail_all(self):
        self.fail_lc = set(ps.LEETCODE_HANDLES)
        self.fail_cf = True


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(ps, "_now", c)
    return c


@pytest.fixture
def fetchers(monkeypatch):
    f = Fetchers()
    monkeypatch.setattr(ps, "fetch_leetcode", f.leetcode)
    monkeypatch.setattr(ps, "fetch_codeforces", f.codeforces)
    monkeypatch.setattr(ps.requests, "get", _no_network)
    monkeypatch.setattr(ps.requests, "post", _no_network)
    return f


def _no_network(*a, **k):
    raise AssertionError("tests must not hit the network")


@pytest.fixture
def client(clock, fetchers):
    ps._CACHE.update(at=0.0, data=None, failed_at=0.0)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    ps._CACHE.update(at=0.0, data=None, failed_at=0.0)


def _stats(client, path="/api/public/stats"):
    res = client.get(path)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["status"] == "success"
    return body["data"]


def test_shape_on_success(client, fetchers):
    data = _stats(client)
    assert set(data) == {"leetcode", "codeforces", "fetched_at"}
    assert set(data["leetcode"]) == {"Sairaghava1318", "Veratril"}
    for entry in data["leetcode"].values():
        assert entry == LC
    assert data["codeforces"] == CF
    assert data["fetched_at"].endswith("Z")
    assert fetchers.calls == 3


def test_cache_control_header(client):
    res = client.get("/api/public/stats")
    assert res.headers["Cache-Control"] == "public, max-age=3600"


def test_one_source_failing_is_null(client, fetchers):
    fetchers.fail_lc = {"Veratril"}
    data = _stats(client)
    assert data["leetcode"]["Veratril"] is None
    assert data["leetcode"]["Sairaghava1318"] == LC
    assert data["codeforces"] == CF


def test_codeforces_failing_is_null(client, fetchers):
    fetchers.fail_cf = True
    data = _stats(client)
    assert data["codeforces"] is None
    assert all(v == LC for v in data["leetcode"].values())


def test_all_failing_with_no_cache_still_200(client, fetchers):
    fetchers.fail_all()
    data = _stats(client)
    assert data["codeforces"] is None
    assert all(v is None for v in data["leetcode"].values())


def test_cache_within_ttl_then_refetch(client, fetchers, clock):
    _stats(client)
    assert fetchers.calls == 3
    fetchers.lc_total = 501
    clock.t += ps.CACHE_TTL - 1
    assert _stats(client)["leetcode"]["Veratril"]["total"] == 500
    assert fetchers.calls == 3  # served from cache
    clock.t += 2
    assert _stats(client)["leetcode"]["Veratril"]["total"] == 501
    assert fetchers.calls == 6


def test_refresh_param_cannot_bust_cache(client, fetchers):
    _stats(client)
    _stats(client, "/api/public/stats?refresh=1")
    assert fetchers.calls == 3


def test_stale_cache_served_when_refetch_fails(client, fetchers, clock):
    first = _stats(client)
    fetchers.fail_all()
    clock.t += ps.CACHE_TTL + 1
    assert _stats(client) == first
    assert fetchers.calls == 6
    # upstream isn't retried on every request while it is down
    clock.t += 60
    assert _stats(client) == first
    assert fetchers.calls == 6


def test_partial_failure_keeps_last_good_value(client, fetchers, clock):
    _stats(client)
    fetchers.fail_cf = True
    fetchers.lc_total = 501
    clock.t += ps.CACHE_TTL + 1
    data = _stats(client)
    assert data["leetcode"]["Veratril"]["total"] == 501
    assert data["codeforces"] == CF


def test_reachable_without_passcode(client, monkeypatch):
    monkeypatch.setenv("APP_PASSCODE", "1234")
    assert client.get("/api/settings").status_code == 401  # the lock is on
    data = _stats(client)
    assert data["codeforces"] == CF


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_fetchers_parse_upstream_payloads(monkeypatch):
    lc_body = {"data": {
        "matchedUser": {"submitStatsGlobal": {"acSubmissionNum": [
            {"difficulty": "All", "count": 10}, {"difficulty": "Easy", "count": 5},
            {"difficulty": "Medium", "count": 4}, {"difficulty": "Hard", "count": 1}]},
            "badges": [{"id": "1"}, {"id": "2"}]},
        "userContestRanking": {"rating": 1745.6, "attendedContestsCount": 12, "topPercentage": 11.2}}}
    cf_body = {"status": "OK", "result": [{"handle": "Raghavan_CP", "rating": 1500, "maxRating": 1550,
                                           "rank": "specialist", "maxRank": "specialist"}]}
    seen = {}

    def post(url, json, headers, timeout):
        seen["lc_timeout"] = timeout
        return FakeResponse(lc_body)

    def get(url, params, headers, timeout):
        seen["cf_timeout"] = timeout
        return FakeResponse(cf_body)

    monkeypatch.setattr(ps.requests, "post", post)
    monkeypatch.setattr(ps.requests, "get", get)
    assert ps.fetch_leetcode("x") == {"total": 10, "easy": 5, "medium": 4, "hard": 1, "contest_rating": 1746,
                                      "contests_attended": 12, "top_percentage": 11.2, "badges": 2}
    assert ps.fetch_codeforces("Raghavan_CP") == {"handle": "Raghavan_CP", "rating": 1500, "max_rating": 1550,
                                                  "rank": "specialist", "max_rank": "specialist"}
    assert seen == {"lc_timeout": ps.TIMEOUT, "cf_timeout": ps.TIMEOUT}

    lc_body["data"]["matchedUser"] = None
    with pytest.raises(ValueError):
        ps.fetch_leetcode("ghost")
