"""Big-tech career-site adapters: parsing, India filter compatibility, error handling. No network."""
import json

import pytest
import requests

from api.domain import job_bigtech as bt
from api.domain import job_sources as js


class FakeResp:
    def __init__(self, payload=None, status=200, text=None, url="https://fake"):
        self._payload, self.status_code, self.url = payload, status, url
        self.text = text if text is not None else json.dumps(payload)
        self.ok = status < 400

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} error")


class Router:
    """Fake get/post: first route whose substring is in the URL wins; records every call."""

    def __init__(self, *routes):
        self.routes, self.calls = list(routes), []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        for needle, resp in self.routes:
            if needle in url:
                return resp(url, kw) if callable(resp) else resp
        raise AssertionError(f"unexpected URL {url}")


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(bt.EightfoldSource, "PAUSE", 0)


def _sent_headers(router):
    return [kw.get("headers") or {} for _u, kw in router.calls]


# ---------------- shared helpers ----------------
def test_date_formats():
    assert bt._date("October  9, 2026") == "2026-10-09"
    assert bt._date("15 Oct 2026") == "2026-10-15"
    assert bt._date("2026-09-24 03:33 PM") == "2026-09-24"
    assert bt._date(1792071276) == "2026-10-15"
    assert bt._date(1792071276000) == "2026-10-15"
    assert bt._date("about 2 hours") == "" and bt._date(None) == ""


def test_india_label():
    assert bt._india("Noida") == "Noida, India"
    assert bt._india("Bengaluru, India") == "Bengaluru, India"
    assert bt._india("") == "India"


def test_registry_is_consistent():
    for name, board, token, band in bt.BIGTECH_COMPANIES + bt.BIGTECH_EXTRA:
        assert board in bt.BIGTECH_SOURCES, name
        assert token and band.endswith("LPA")
    assert all(s.name == k for k, s in bt.BIGTECH_SOURCES.items())
    # merging into job_sources.SOURCES must not replace an existing board type
    # registered into the scanner without replacing the standard boards
    assert all(js.SOURCES[k] is v for k, v in bt.BIGTECH_SOURCES.items())
    assert {"greenhouse", "lever", "ashby", "smartrecruiters", "workday"} <= set(js.SOURCES) - set(bt.BIGTECH_SOURCES)
    assert "Google" not in {c[0] for c in bt.BIGTECH_COMPANIES}  # opt-in only


# ---------------- Amazon ----------------
AMAZON = {"error": None, "hits": 2, "jobs": [
    {"id_icims": "10580071", "title": "Software Development Engineer I", "normalized_location": "Hyderabad, Telangana, IND",
     "job_path": "/en/jobs/10580071/sde-i", "description": "Build <b>distributed</b> systems in Java and Python.",
     "basic_qualifications": "- Bachelor's degree<br/>- 2026 or 2027 graduate", "preferred_qualifications": None,
     "posted_date": "October  9, 2026"},
    {"id_icims": "10580072", "title": "Senior Software Development Engineer", "normalized_location": "Kochi, Kerala, IND",
     "job_path": "/en/jobs/10580072/sr", "description": "", "posted_date": "October 1, 2026"},
]}


def test_amazon_parses_and_filters():
    get = Router(("amazon.jobs/en/search.json", FakeResp(AMAZON)))
    ps = bt.AmazonSource().list_postings("Amazon", "software-development", get=get)
    assert len(ps) == 2 and len(get.calls) == 1
    url, kw = get.calls[0]
    assert "country=IND" in url and "category%5B%5D=software-development" in url and kw["timeout"] == bt.TIMEOUT
    assert "User-Agent" in kw["headers"]
    p = ps[0]
    assert (p.job_id, p.location, p.posted) == ("10580071", "Hyderabad, Telangana, India", "2026-10-09")
    assert p.url == "https://www.amazon.jobs/en/jobs/10580071/sde-i"
    assert "distributed systems" in p.text and "<b>" not in p.text
    assert js.is_india(p) and js.is_candidate_role(p)
    assert ps[1].location == "Kochi, Kerala, India" and js.is_india(ps[1]) and not js.is_candidate_role(ps[1])


def test_amazon_errors():
    with pytest.raises(requests.HTTPError):
        bt.AmazonSource().list_postings("Amazon", "x", get=Router(("amazon", FakeResp({}, status=503))))
    with pytest.raises(ValueError):
        bt.AmazonSource().list_postings("Amazon", "x", get=Router(("amazon", FakeResp({"error": "bad", "jobs": []}))))
    with pytest.raises(ValueError):  # HTML instead of JSON (e.g. an error page)
        bt.AmazonSource().list_postings("Amazon", "x", get=Router(("amazon", FakeResp(None, text="<html>"))))


# ---------------- Eightfold (Microsoft / Qualcomm) ----------------
def _ef_page(start, n, count=15):
    return {"status": 200, "data": {"count": count, "positions": [
        {"id": 1000 + start + i, "displayJobId": str(2000 + start + i), "name": f"Software Engineer {i}" if i else "Software Engineer",
         "locations": ["India, Karnataka, Bangalore", "United States, Washington, Redmond"], "postedTs": 1792071276,
         "department": "Software Engineering", "positionUrl": f"/careers/job/{1000 + start + i}"} for i in range(n)]}}


def test_eightfold_pages_and_parses():
    get = Router(("start=0", FakeResp(_ef_page(0, 10))), ("start=10", FakeResp(_ef_page(10, 5))))
    ps = bt.EightfoldSource().list_postings("Microsoft", "apply.careers.microsoft.com|microsoft.com", get=get)
    assert len(ps) == 15 and len(get.calls) == 2
    assert "domain=microsoft.com" in get.calls[0][0] and "location=India" in get.calls[0][0]
    p = ps[0]
    assert p.location == "India, Karnataka, Bangalore"  # US location dropped
    assert p.url == "https://apply.careers.microsoft.com/careers/job/1000" and p.posted == "2026-10-15"
    assert js.is_india(p) and js.is_candidate_role(p)


def test_eightfold_stops_at_count():
    get = Router(("start=0", FakeResp(_ef_page(0, 10, count=10))))
    assert len(bt.EightfoldSource().list_postings("Q", "careers.qualcomm.com|qualcomm.com", get=get)) == 10
    assert len(get.calls) == 1


def test_eightfold_rate_limit():
    get = Router(("start=0", FakeResp(_ef_page(0, 10))), ("start=10", FakeResp(None, status=429, text="")))
    assert len(bt.EightfoldSource().list_postings("Microsoft", "h|d", get=get)) == 10  # keeps page 1
    with pytest.raises(requests.HTTPError):
        bt.EightfoldSource().list_postings("Microsoft", "h|d", get=Router(("start=0", FakeResp(None, status=429, text=""))))


def test_eightfold_details():
    p = bt.EightfoldSource().list_postings("M", "h.com|d.com", get=Router(("start=0", FakeResp(_ef_page(0, 1, 1)))))[0]
    get = Router(("position_details", FakeResp({"data": {"jobDescription": "<p>2+ years of C++</p>"}})))
    assert bt.EightfoldSource().details(p, get=get).text == "2+ years of C++"
    assert "position_id=1000" in get.calls[0][0]
    p.text = ""
    bt.EightfoldSource().details(p, get=Router(("position_details", FakeResp(None, status=500, text=""))))
    assert p.text == ""  # failure leaves the posting untouched


# ---------------- Apple ----------------
APPLE = {"res": {"totalRecords": 2, "searchResults": [
    {"id": "200687173-1052", "positionId": "200687173", "postingTitle": "Software Engineer : AI",
     "transformedPostingTitle": "software-engineer-ai", "jobSummary": "Build ML infra in Python.",
     "postDateInGMT": "2026-10-15T10:13:25.791Z", "team": {"teamName": "Software and Services"},
     "locations": [{"name": "Hyderabad", "countryName": "India", "countryID": "iso-country-IND"}]},
    {"id": "1-1", "positionId": "1", "postingTitle": "IN-Genius", "transformedPostingTitle": "in-genius",
     "jobSummary": "", "postDateInGMT": "", "locations": [{"name": "India", "countryName": "India", "countryID": "iso-country-IND"}]},
]}}


def test_apple_parses():
    post = Router(("jobs.apple.com/api/v1/search", FakeResp(APPLE)))
    ps = bt.AppleSource().list_postings("Apple", "postLocation-INDC", post=post)
    assert len(ps) == 2 and len(post.calls) == 1  # totalRecords reached -> no second page
    body = post.calls[0][1]["json"]
    assert body["filters"] == {"locations": ["postLocation-INDC"]} and body["page"] == 1
    p = ps[0]
    assert (p.location, p.posted, p.job_id) == ("Hyderabad, India", "2026-10-15", "200687173-1052")
    assert p.url == "https://jobs.apple.com/en-in/details/200687173/software-engineer-ai"
    assert js.is_india(p) and js.is_candidate_role(p)
    assert ps[1].location == "India" and not js.is_candidate_role(ps[1])


def test_apple_error():
    with pytest.raises(requests.HTTPError):
        bt.AppleSource().list_postings("Apple", "x", post=Router(("apple", FakeResp({}, status=403))))


# ---------------- Atlassian ----------------
ATLASSIAN = [
    {"id": 1, "title": "Software Engineer, Graduate", "category": "Engineering",
     "locations": ["Bengaluru - India -   Bengaluru,  560071 India", "Remote - India - Remote", "Remote - Remote"],
     "overview": "<p>Join us</p>", "responsibilities": "<ul><li>Build Jira</li></ul>", "qualifications": "Java, React",
     "applyUrl": "https://careers.example/apply/1", "portalJobPost": {"updatedDate": "2026-09-24 03:33 PM"}},
    {"id": 2, "title": "Software Engineer", "locations": ["Sydney - Australia - Sydney"], "portalJobPost": {}},
]


def test_atlassian_keeps_india_only():
    ps = bt.AtlassianSource().list_postings("Atlassian", "all", get=Router(("atlassian.com", FakeResp(ATLASSIAN))))
    assert len(ps) == 1
    p = ps[0]
    assert p.location == "Bengaluru, India / Remote, India" and p.posted == "2026-09-24"
    assert "Build Jira" in p.text and p.url == "https://careers.example/apply/1"
    assert js.is_india(p) and js.is_candidate_role(p)


def test_atlassian_bad_shape():
    with pytest.raises(ValueError):
        bt.AtlassianSource().list_postings("Atlassian", "all", get=Router(("atlassian", FakeResp({"jobs": []}))))


# ---------------- Goldman Sachs ----------------
GS = {"data": {"roleSearch": {"totalCount": 2, "items": [
    {"roleId": "174521_GS_EARLY_CAREER", "jobTitle": "The Core Engineering-Hyderabad-Analyst-Software Engineering",
     "corporateTitle": "Analyst", "shortDescription": "TheÂ Platform team builds Java services.",
     "lastPostedDate": "2026-09-23T05:23:27.787Z", "status": "ACTIVE",
     "locations": [{"city": "Hyderabad", "country": "India"}], "externalSource": {"sourceId": "174521"}},
    {"roleId": "x", "jobTitle": "Software Engineer", "locations": [{"city": "London", "country": "United Kingdom"}],
     "externalSource": {"sourceId": "9"}},
]}}}


def test_goldman_parses():
    post = Router(("api-higher.gs.com", FakeResp(GS)))
    ps = bt.GoldmanSource().list_postings("Goldman Sachs", "software", post=post)
    assert len(ps) == 1
    sent = post.calls[0][1]["json"]["variables"]["searchQueryInput"]
    assert sent["searchTerm"] == "software" and sent["filters"][0]["filters"][0]["filter"] == "India"
    p = ps[0]
    assert (p.job_id, p.location, p.posted) == ("174521", "Hyderabad, India", "2026-09-23")
    assert p.url == "https://higher.gs.com/roles/174521"
    assert p.text == "The Platform team builds Java services."  # double-encoded nbsp repaired
    assert p.meta["early_career"] is True and js.is_india(p)


def test_goldman_graphql_error():
    with pytest.raises(ValueError, match="GS GraphQL"):
        bt.GoldmanSource().list_postings("GS", "software", post=Router(("gs.com", FakeResp({"errors": [{"message": "bad"}]}))))


# ---------------- Oracle Recruiting Cloud ----------------
ORC = {"items": [{"TotalJobsCount": 2, "requisitionList": [
    {"Id": "210774164", "Title": "Software Engineer I - Java", "PrimaryLocation": "Bengaluru, Karnataka, India",
     "PostedDate": "2026-10-15", "ShortDescriptionStr": "Kafka and <b>Spring</b>",
     "secondaryLocations": [{"Name": "Pune, Maharashtra, India"}, {"Name": "Plano, TX, United States"}]},
    {"Id": "347670", "Title": "Senior Fusion Application Developer", "PrimaryLocation": "India", "PostedDate": "2026-10-15",
     "secondaryLocations": []},
]}]}


def test_oracle_hcm_parses():
    get = Router(("recruitingCEJobRequisitions?", FakeResp(ORC)))
    ps = bt.OracleHCMSource().list_postings("JPMorgan Chase", "jpmc.fa.oraclecloud.com|CX_1001|3000|software", get=get)
    url = get.calls[0][0]
    assert "siteNumber=CX_1001" in url and "locationId=3000" in url and "keyword=%22software%22" in url
    p = ps[0]
    assert p.location == "Bengaluru, Karnataka, India / Pune, Maharashtra, India"
    assert p.url == "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/210774164"
    assert p.posted == "2026-10-15" and p.text == "Kafka and Spring"
    assert js.is_india(p) and js.is_candidate_role(p) and not js.is_candidate_role(ps[1])


def test_oracle_hcm_no_keyword_and_details():
    get = Router(("recruitingCEJobRequisitions?", FakeResp({"items": []})))
    assert bt.OracleHCMSource().list_postings("Oracle", "eeho.fa.us2.oraclecloud.com|CX_45001|1|", get=get) == []
    assert "keyword" not in get.calls[0][0]
    p = bt.OracleHCMSource().list_postings("J", "h.com|S|1|x", get=Router(("Requisitions?", FakeResp(ORC))))[0]
    det = Router(("recruitingCEJobRequisitionDetails", FakeResp({"items": [
        {"ExternalDescriptionStr": "<p>0-1 years</p>", "ExternalQualificationsStr": "B.Tech"}]})))
    assert bt.OracleHCMSource().details(p, get=det).text == "0-1 years B.Tech"
    assert "Id=%22210774164%22" in det.calls[0][0] and "siteNumber=S" in det.calls[0][0]
    with pytest.raises(requests.HTTPError):
        bt.OracleHCMSource().list_postings("J", "h|S|1|", get=Router(("h", FakeResp({}, status=500))))


# ---------------- Workday ----------------
def _wd(jobs, total=None, facets=None):
    return {"total": len(jobs) if total is None else total, "jobPostings": jobs, "facets": facets or []}


WD_JOB = {"title": "Software Engineer", "externalPath": "/job/Bangalore/Software-Engineer_R1", "locationsText": "2 Locations",
          "postedOn": "Posted 3 Days Ago", "bulletFields": ["R1"]}


def test_workday_explicit_facet_one_request():
    post = Router(("/jobs", FakeResp(_wd([WD_JOB]))))
    ps = bt.WorkdaySource().list_postings("Samsung R&D", "sec|wd3|Samsung_Careers|Location_Country=abc", post=post)
    assert len(post.calls) == 1
    url, kw = post.calls[0]
    assert url == "https://sec.wd3.myworkdayjobs.com/wday/cxs/sec/Samsung_Careers/jobs"
    assert kw["json"]["appliedFacets"] == {"Location_Country": ["abc"]}
    p = ps[0]
    assert (p.job_id, p.location) == ("R1", "2 Locations, India")
    assert p.url == "https://sec.wd3.myworkdayjobs.com/en-US/Samsung_Careers/job/Bangalore/Software-Engineer_R1"
    assert js.is_india(p) and js.is_candidate_role(p)


def test_workday_discovers_india_facet_and_pages():
    facets = [{"facetParameter": "locations", "values": [{"descriptor": "Bangalore, India", "id": "blr"},
                                                         {"descriptor": "Austin, TX", "id": "aus"}]},
              {"facetParameter": "locationMainGroup", "values": [
                  {"facetParameter": "locationCountry", "values": [{"descriptor": "India", "id": "IN"}]}]}]
    pages = iter([FakeResp(_wd([WD_JOB], total=100, facets=facets)),          # discovery
                  FakeResp(_wd([WD_JOB] * 20, total=25)),                       # India page 1
                  FakeResp(_wd([WD_JOB] * 5, total=0))])                        # page 2 (total only on page 1)
    post = Router(("/jobs", lambda u, kw: next(pages)))
    ps = bt.WorkdaySource().list_postings("Adobe", "adobe|wd5|external_experienced", post=post)
    assert len(ps) == 25 and len(post.calls) == 3
    assert post.calls[1][1]["json"]["appliedFacets"] == {"locationCountry": ["IN"]}  # country beats city values
    assert post.calls[2][1]["json"]["offset"] == 20


def test_workday_no_location_facet_keeps_first_page_raw():
    job = dict(WD_JOB, locationsText="Austin, TX")
    ps = bt.WorkdaySource().list_postings("X", "x|wd1|S", post=Router(("/jobs", FakeResp(_wd([job])))))
    assert ps[0].location == "Austin, TX" and not js.is_india(ps[0])


def test_workday_details_and_error():
    p = bt.WorkdaySource().list_postings("S", "sec|wd3|S|k=v", post=Router(("/jobs", FakeResp(_wd([WD_JOB])))))[0]
    get = Router(("/job/Bangalore", FakeResp({"jobPostingInfo": {"jobDescription": "<p>Freshers welcome</p>",
                                                                 "startDate": "2026-10-12"}})))
    bt.WorkdaySource().details(p, get=get)
    assert p.text == "Freshers welcome" and p.posted == "2026-10-12"
    with pytest.raises(requests.HTTPError):
        bt.WorkdaySource().list_postings("S", "sec|wd3|S", post=Router(("/jobs", FakeResp({}, status=422))))


# ---------------- Google (opt-in) ----------------
def _google_page(rows):
    blob = json.dumps([rows, None, len(rows), 20])
    return (f"<html><script>AF_initDataCallback({{key: 'ds:0', hash: '1', data:[1], sideChannel: {{}}}});</script>"
            f"<script>AF_initDataCallback({{key: 'ds:1', hash: '2', data:{blob}, sideChannel: {{}}}});</script></html>")


def _g_row(jid, title, locs):
    row = [None] * 21
    row[0], row[1] = jid, title
    row[3], row[4], row[10] = [None, "<li>Write code</li>"], [None, "Bachelor's degree"], [None, "<p>About</p>"]
    row[9] = [[l, [], "", "", "", ""] for l in locs]
    row[12] = [1792071276, 0]
    return row


def test_google_parses_blob():
    html_text = _google_page([_g_row("123", "Software Engineer II, Infrastructure", ["Bengaluru, Karnataka, India"]),
                              _g_row("456", "Software Engineer", ["Zurich, Switzerland"])])
    get = Router(("google.com/about/careers", FakeResp(None, text=html_text)))
    ps = bt.GoogleSource().list_postings("Google", "EARLY", get=get)
    assert len(ps) == 1 and "target_level=EARLY" in get.calls[0][0] and "location=India" in get.calls[0][0]
    p = ps[0]
    assert p.job_id == "123" and p.location == "Bengaluru, Karnataka, India" and p.posted == "2026-10-15"
    assert p.url.endswith("/123-software-engineer-ii-infrastructure") and "Write code" in p.text
    assert js.is_india(p)


def test_google_layout_change_raises():
    with pytest.raises(ValueError, match="blob not found"):
        bt.GoogleSource().list_postings("Google", "EARLY", get=Router(("google", FakeResp(None, text="<html></html>"))))


# ---------------- plugs into job_sources.collect ----------------
def test_collect_with_bigtech_sources(monkeypatch):
    for name, src in bt.BIGTECH_SOURCES.items():
        monkeypatch.setitem(js.SOURCES, name, src)
    monkeypatch.setattr(js, "is_fresh", lambda p, today=None: True)
    get = Router(("amazon.jobs/en/search.json", FakeResp(AMAZON)), ("atlassian.com", FakeResp(ATLASSIAN)))
    scored, errors = js.collect(get=get, post=Router(), companies=[("Amazon", "amazon", "software-development"),
                                                                   ("Atlassian", "atlassian", "all")])
    titles = {p.title for p, *_ in scored}
    assert errors == []
    assert titles == {"Software Development Engineer I", "Software Engineer, Graduate"}
