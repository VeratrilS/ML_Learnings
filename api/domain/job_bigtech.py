"""
Big-company career sites for Job Radar (companies that run their OWN careers search, not Greenhouse/Lever/Ashby).

Each adapter calls the same public JSON endpoint the company's careers website calls from the browser: no login,
no captcha, no HTML scraping behind bot protection. One request per search page, TIMEOUT s each, a User-Agent set,
and searches are already scoped to India (+ software) server-side wherever the API allows it. Results are
normalized to job_sources.Posting so collect() can run its usual is_india / is_candidate_role / is_fresh / score.

Plug-in (done later in job_sources.py):
    SOURCES.update(BIGTECH_SOURCES)
    COMPANIES += [(n, b, t) for n, b, t, _band in BIGTECH_COMPANIES]   # band -> CTC_BAND, like NEXTLEET_COMPANIES

Verified live on 2026-10-16. Numbers = India postings one scan returned / of those, software-titled /
of those, early-career candidates (job_sources.is_candidate_role):
    Amazon          amazon.jobs/en/search.json  country=IND, category=software-development  100 / 98 / 36  (404 open)
    Microsoft       apply.careers.microsoft.com/api/pcsx/search (Eightfold), 2 pages      20 / 16 / 4   (123 open)
    Qualcomm        careers.qualcomm.com/api/pcsx/search (Eightfold), 2 pages             20 / 20 / 8   (474 open)
    Apple           jobs.apple.com/api/v1/search  POST, filter postLocation-INDC, 2 pages  40 / 33 / 26  (126 open)
    Atlassian       atlassian.com/endpoint/careers/listings  (all 353 jobs, India kept)    44 / 24 / 3
    Goldman Sachs   api-higher.gs.com/gateway/api/v1/graphql  roleSearch, LOCATION=India   40 / 15 / 7
    JPMorgan Chase  jpmc.fa.oraclecloud.com  Oracle Recruiting REST, CX_1001, India       100 / 73 / 0   (106 open)
    Texas Instr.    edbz.fa.us2.oraclecloud.com  Oracle Recruiting REST, CX, India        100 / 81 / 63
    Oracle          eeho.fa.us2.oraclecloud.com  Oracle Recruiting REST, CX_45001, India   14 / 2 / 0
    Samsung R&D     sec.wd3.myworkdayjobs.com  Samsung_Careers (Workday CXS)                8 / 3 / 3
  Already scanned by job_sources.COMPANIES through its WorkdaySource (verified the same day, so not repeated
  here): Salesforce, Adobe, NVIDIA, Intel, Cisco, PayPal, Visa, Morgan Stanley.
  Opt-in only (BIGTECH_EXTRA, not in BIGTECH_COMPANIES):
    Google          google.com/about/careers/applications/jobs/results — no public JSON endpoint; the search page
                    server-renders its results as a JSON blob (AF_initDataCallback 'ds:1'), parsed here.  14 / 11 / 6
Not built (checked 2026-10-16):
    Uber (careers pages and loadSearchJobsResults RPC return 404 to non-browser clients), Walmart / Flipkart /
    PhonePe (no public JSON search found; their Workday tenants do not exist), D. E. Shaw (jobs only embedded in a
    2 MB Next.js page, no endpoint), Google's old careers.google.com/api/v3 (404).

Counts are what one scan of each search returned that day, not the employer's total; "software-titled" =
job_sources.ROLE matches and NOT_SWE doesn't.
"""
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from api.domain.job_sources import BoardSource, Posting, _plain

TIMEOUT = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36 JobRadar/1.0 (personal job search)",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",  # amazon.jobs answers zstd otherwise, which requests can't always decode
}
JSON_POST = {**HEADERS, "Content-Type": "application/json"}
ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
INDIA_WORD = re.compile(r"\bindia\b", re.I)


def _date(value):
    """ISO string / epoch s or ms / 'October  9, 2026' / '15 Oct 2026' -> 'YYYY-MM-DD' ('' when unknown)."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)) or str(value).isdigit():
        ts = float(value)
        return datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, timezone.utc).date().isoformat()
    s = re.sub(r"\s+", " ", str(value)).strip()
    m = ISO.search(s)
    if m:
        return "-".join(m.groups())
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def _india(loc):
    """The search was India-scoped server-side: make sure the label says so (job_sources.is_india reads it)."""
    loc = (loc or "").strip()
    return loc if INDIA_WORD.search(loc) else (f"{loc}, India" if loc else "India")


def _json(r):
    r.raise_for_status()
    try:
        return r.json()
    except ValueError as e:
        raise ValueError(f"non-JSON response from {getattr(r, 'url', '?')}") from e


# ---------------- Amazon ----------------
class AmazonSource(BoardSource):
    """amazon.jobs search.json. token = job category slug (e.g. 'software-development'). Newest 100 in India."""
    name = "amazon"
    URL = "https://www.amazon.jobs/en/search.json"
    LIMIT = 100

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        q = f"?country=IND&category%5B%5D={quote(token)}&result_limit={self.LIMIT}&sort=recent&offset=0"
        d = _json(get(self.URL + q, headers=HEADERS, timeout=TIMEOUT))
        if d.get("error"):
            raise ValueError(f"amazon.jobs error: {d['error']}")
        out = []
        for j in d.get("jobs") or []:
            loc = re.sub(r",\s*IND$", ", India", j.get("normalized_location") or j.get("location") or "")
            text = " ".join(j.get(k) or "" for k in ("description", "basic_qualifications", "preferred_qualifications"))
            out.append(Posting(company, self.name, str(j.get("id_icims") or j.get("id") or ""), j.get("title", ""),
                               _india(loc), "https://www.amazon.jobs" + (j.get("job_path") or ""), _plain(text),
                               j.get("posted_date", ""), posted=_date(j.get("posted_date"))))
        return [p for p in out if p.job_id and p.title]


# ---------------- Eightfold (Microsoft, Qualcomm) ----------------
class EightfoldSource(BoardSource):
    """Eightfold 'pcsx' careers API. token = 'host|domain' (e.g. 'apply.careers.microsoft.com|microsoft.com').

    10 results per page, newest first; PAGES pages max. Microsoft rate-limits hard (429 after ~4 quick calls),
    so a 429 after the first page keeps what was already fetched.
    """
    name = "eightfold"
    QUERY = "software engineer"
    PAGES = 2
    PAGE = 10
    PAUSE = 3.0  # s between pages; back-to-back calls get 429 from Microsoft

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        host, domain = token.split("|")
        out = []
        for page in range(self.PAGES):
            if page:
                time.sleep(self.PAUSE)
            url = (f"https://{host}/api/pcsx/search?domain={domain}&query={quote(self.QUERY)}&location=India"
                   f"&start={page * self.PAGE}&sort_by=timestamp")
            r = get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 429 and out:
                break
            data = (_json(r).get("data") or {})
            jobs = data.get("positions") or []
            for j in jobs:
                locs = j.get("locations") or j.get("standardizedLocations") or []
                india = [l for l in locs if INDIA_WORD.search(l) or l.endswith(", IN")] or locs
                pid = str(j.get("id", ""))
                out.append(Posting(company, self.name, str(j.get("displayJobId") or pid), j.get("name", ""),
                                   _india(" / ".join(india)), f"https://{host}" + (j.get("positionUrl") or f"/careers/job/{pid}"),
                                   updated=str(j.get("postedTs") or ""), posted=_date(j.get("postedTs")),
                                   meta={"host": host, "domain": domain, "pid": pid, "dept": j.get("department") or ""}))
            if len(jobs) < self.PAGE or len(out) >= (data.get("count") or 0):
                break
        return [p for p in out if p.title]

    def details(self, posting, get=requests.get):
        m = posting.meta
        try:
            r = get(f"https://{m['host']}/api/pcsx/position_details?position_id={m['pid']}&domain={m['domain']}&hl=en",
                    headers=HEADERS, timeout=TIMEOUT)
            if r.ok:
                posting.text = _plain((r.json().get("data") or {}).get("jobDescription", ""))
        except Exception:
            pass
        return posting


# ---------------- Apple ----------------
class AppleSource(BoardSource):
    """jobs.apple.com/api/v1/search (POST). token = location filter id ('postLocation-INDC' = India). 20/page."""
    name = "apple"
    URL = "https://jobs.apple.com/api/v1/search"
    QUERY = "software"
    PAGES = 2

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        out = []
        for page in range(1, self.PAGES + 1):
            body = {"query": self.QUERY, "filters": {"locations": [token]}, "page": page, "locale": "en-in",
                    "sort": "newest", "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"}}
            res = _json(post(self.URL, json=body, headers=JSON_POST, timeout=TIMEOUT)).get("res") or {}
            jobs = res.get("searchResults") or []
            for j in jobs:
                locs = []
                for l in j.get("locations") or []:
                    if (l.get("countryID") or "").endswith("-IND") or (l.get("countryName") or "") == "India":
                        locs.append(_india(l.get("name") or ""))
                pid = j.get("positionId") or j.get("id") or ""
                out.append(Posting(company, self.name, str(j.get("id") or pid), j.get("postingTitle", ""),
                                   _india(" / ".join(dict.fromkeys(locs))),
                                   f"https://jobs.apple.com/en-in/details/{pid}/{j.get('transformedPostingTitle', '')}",
                                   _plain(j.get("jobSummary", "")), j.get("postDateInGMT", ""),
                                   posted=_date(j.get("postDateInGMT")),
                                   meta={"team": (j.get("team") or {}).get("teamName", "")}))
            if len(out) >= (res.get("totalRecords") or 0) or not jobs:
                break
        return [p for p in out if p.title]


# ---------------- Atlassian ----------------
class AtlassianSource(BoardSource):
    """atlassian.com/endpoint/careers/listings: every open job in one JSON list; India ones kept. token unused."""
    name = "atlassian"
    URL = "https://www.atlassian.com/endpoint/careers/listings"

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        d = _json(get(self.URL, headers=HEADERS, timeout=TIMEOUT))
        if not isinstance(d, list):
            raise ValueError("atlassian listings: expected a list")
        out = []
        for j in d:
            # 'Bengaluru - India -   Bengaluru,  560071 India' / 'Remote - India - Remote' -> 'Bengaluru, India'
            india = list(dict.fromkeys(f"{l.split(' - ')[0].strip()}, India" for l in j.get("locations") or []
                                       if INDIA_WORD.search(l)))
            if not india:
                continue
            portal = j.get("portalJobPost") or {}
            text = " ".join(j.get(k) or "" for k in ("overview", "responsibilities", "qualifications"))
            out.append(Posting(company, self.name, str(j.get("id", "")), j.get("title", ""), " / ".join(india),
                               j.get("applyUrl") or portal.get("portalUrl", ""), _plain(text),
                               portal.get("updatedDate", ""), posted=_date(portal.get("updatedDate")),
                               meta={"category": j.get("category") or ""}))
        return [p for p in out if p.title]


# ---------------- Goldman Sachs ----------------
class GoldmanSource(BoardSource):
    """higher.gs.com's GraphQL gateway (public, no auth). token = searchTerm. One page of 50, India only."""
    name = "goldman"
    URL = "https://api-higher.gs.com/gateway/api/v1/graphql"
    QUERY = ("query GetRoles($searchQueryInput: RoleSearchQueryInput!) { roleSearch(searchQueryInput: $searchQueryInput)"
             " { totalCount items { roleId jobTitle corporateTitle jobFunction division shortDescription"
             " lastPostedDate status locations { city country } externalSource { sourceId } } } }")
    SIZE = 50

    @staticmethod
    def _fix(s):
        """GS descriptions arrive double-encoded ('TheÂ\xa0team'); undo when that's what happened."""
        if s and "Â" in s:
            try:
                return s.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return s or ""

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        variables = {"searchQueryInput": {
            "page": {"pageSize": self.SIZE, "pageNumber": 0}, "searchTerm": token,
            "filters": [{"filterCategoryType": "LOCATION", "filters": [{"filter": "India", "subFilters": []}]}],
            "experiences": ["EARLY_CAREER", "PROFESSIONAL"]}}
        d = _json(post(self.URL, json={"operationName": "GetRoles", "query": self.QUERY, "variables": variables},
                       headers=JSON_POST, timeout=TIMEOUT))
        if d.get("errors"):
            raise ValueError(f"GS GraphQL: {str(d['errors'][0].get('message', ''))[:80]}")
        out = []
        for j in ((d.get("data") or {}).get("roleSearch") or {}).get("items") or []:
            locs = [", ".join(x for x in (l.get("city"), l.get("country")) if x) for l in j.get("locations") or []]
            india = [l for l in locs if INDIA_WORD.search(l)]
            if not india:
                continue
            sid = str((j.get("externalSource") or {}).get("sourceId") or j.get("roleId") or "")
            title = j.get("jobTitle", "")
            out.append(Posting(company, self.name, sid, title, " / ".join(india), f"https://higher.gs.com/roles/{sid}",
                               _plain(self._fix(j.get("shortDescription"))), j.get("lastPostedDate", ""),
                               posted=_date(j.get("lastPostedDate")),
                               meta={"corporate_title": j.get("corporateTitle") or "", "status": j.get("status") or "",
                                     "early_career": "EARLY_CAREER" in (j.get("roleId") or "")}))
        return [p for p in out if p.title and p.job_id]


# ---------------- Oracle Recruiting Cloud (JPMorgan, TI, Oracle) ----------------
class OracleHCMSource(BoardSource):
    """Oracle Recruiting Cloud 'CandidateExperience' REST. token = 'host|siteNumber|locationId|keyword' (keyword
    may be empty). locationId is the site's 'India' location facet id. One request of up to 100, newest first."""
    name = "oraclehcm"
    LIMIT = 100

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        host, site, loc_id, keyword = (token.split("|") + ["", ""])[:4]
        finder = f"findReqs;siteNumber={site},limit={self.LIMIT},sortBy=POSTING_DATES_DESC"
        if loc_id:
            finder += f",locationId={loc_id}"
        if keyword:
            finder += f",keyword=%22{quote(keyword)}%22"
        url = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
               f"&expand=requisitionList.secondaryLocations&finder={finder}")
        items = _json(get(url, headers=HEADERS, timeout=TIMEOUT)).get("items") or []
        out = []
        for j in (items[0].get("requisitionList") or []) if items else []:
            locs = [j.get("PrimaryLocation") or ""] + [l.get("Name") or "" for l in j.get("secondaryLocations") or []]
            india = [l for l in dict.fromkeys(locs) if INDIA_WORD.search(l)]
            rid = str(j.get("Id", ""))
            out.append(Posting(company, self.name, rid, j.get("Title", ""),
                               " / ".join(india) if india else _india(locs[0]) if loc_id else locs[0],
                               f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{rid}",
                               _plain(j.get("ShortDescriptionStr") or ""), j.get("PostedDate", ""),
                               posted=_date(j.get("PostedDate")), meta={"host": host, "site": site}))
        return [p for p in out if p.title and p.job_id]

    def details(self, posting, get=requests.get):
        m = posting.meta
        try:
            r = get(f"https://{m['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all"
                    f"&onlyData=true&finder=ById;Id=%22{posting.job_id}%22,siteNumber={m['site']}",
                    headers=HEADERS, timeout=TIMEOUT)
            if r.ok:
                items = r.json().get("items") or [{}]
                d = items[0]
                text = " ".join(d.get(k) or "" for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr",
                                                          "ExternalQualificationsStr"))
                posting.text = _plain(text) or posting.text
        except Exception:
            pass
        return posting


# ---------------- Workday ----------------
class WorkdaySource(BoardSource):
    """Generic Workday CXS career site. token = 'tenant|wdN|site' or 'tenant|wdN|site|facetParam=id1,id2'.

    With an explicit facet: one POST per page. Without: the first POST returns the facet tree, the India country
    facet (or every India-city location value) is applied, then pages are fetched. 20 per page, PAGES max.
    (job_sources.py has its own WorkdaySource with the same token format; this one keeps job_bigtech standalone.)
    """
    name = "workday_bt"
    SEARCH_TEXT = "software"
    PAGE, PAGES = 20, 3

    @staticmethod
    def india_facet(facets):
        country, cities = {}, {}

        def walk(fs):
            for f in fs or []:
                param = f.get("facetParameter", "")
                for v in f.get("values") or []:
                    if "values" in v:
                        walk([v])
                        continue
                    desc = (v.get("descriptor") or "").strip()
                    if desc.lower() == "india":
                        country.setdefault(param, []).append(v.get("id"))
                    elif INDIA_WORD.search(desc):
                        cities.setdefault(param, []).append(v.get("id"))
        walk(facets)
        for found in (country, cities):
            if found:
                param = max(found, key=lambda p: len(found[p]))
                return {param: found[param]}
        return {}

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        parts = token.split("|")
        tenant, wd, site = parts[:3]
        host = f"https://{tenant}.{wd}.myworkdayjobs.com"
        api = f"{host}/wday/cxs/{tenant}/{site}"
        facet = {}
        if len(parts) > 3 and "=" in parts[3]:
            key, ids = parts[3].split("=", 1)
            facet = {key: ids.split(",")}
        body = {"appliedFacets": facet, "limit": self.PAGE, "offset": 0, "searchText": self.SEARCH_TEXT}
        d = _json(post(f"{api}/jobs", json=body, headers=JSON_POST, timeout=TIMEOUT))
        if not facet:
            facet = self.india_facet(d.get("facets"))
            if not facet:  # no location facet: first page only, India decided later by is_india()
                return [self._posting(company, j, host, api, site, False) for j in d.get("jobPostings") or []]
            body["appliedFacets"] = facet
            d = _json(post(f"{api}/jobs", json=body, headers=JSON_POST, timeout=TIMEOUT))
        total = d.get("total") or 0  # Workday only reports total on the first page
        out = [self._posting(company, j, host, api, site, True) for j in d.get("jobPostings") or []]
        for page in range(1, self.PAGES):
            if len(out) >= total or len(out) < page * self.PAGE:
                break
            body["offset"] = page * self.PAGE
            jobs = _json(post(f"{api}/jobs", json=body, headers=JSON_POST, timeout=TIMEOUT)).get("jobPostings") or []
            out += [self._posting(company, j, host, api, site, True) for j in jobs]
        return [p for p in out if p.title]

    def _posting(self, company, j, host, api, site, india):
        path = j.get("externalPath") or ""
        bullets = j.get("bulletFields") or []
        loc = j.get("locationsText") or ""
        return Posting(company, self.name, str(bullets[0] if bullets else path.rsplit("/", 1)[-1]), j.get("title", ""),
                       _india(loc) if india else loc, f"{host}/en-US/{site}{path}", updated=j.get("postedOn", ""),
                       meta={"api": api, "path": path})

    def details(self, posting, get=requests.get):
        try:
            r = get(f"{posting.meta['api']}{posting.meta['path']}", headers=HEADERS, timeout=TIMEOUT)
            if r.ok:
                info = r.json().get("jobPostingInfo") or {}
                posting.text = _plain(info.get("jobDescription", ""))
                posting.posted = _date(info.get("startDate")) or posting.posted
        except Exception:
            pass
        return posting


# ---------------- Google (opt-in: no JSON endpoint, see module docstring) ----------------
class GoogleSource(BoardSource):
    """Google careers search page; its results ship as JSON inside AF_initDataCallback({key: 'ds:1', ...}).
    token = target level ('EARLY' = new grad / early career). One request, up to 20 newest India results."""
    name = "google"
    URL = "https://www.google.com/about/careers/applications/jobs/results"
    BLOB = re.compile(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*?), sideChannel", re.S)

    def list_postings(self, company, token, get=requests.get, post=requests.post):
        q = f"?location=India&q={quote('software engineer')}&sort_by=date" + (f"&target_level={token}" if token else "")
        r = get(self.URL + q, headers={**HEADERS, "Accept": "text/html"}, timeout=TIMEOUT)
        r.raise_for_status()
        m = self.BLOB.search(r.text)
        if not m:
            raise ValueError("google careers: results blob not found (page layout changed)")
        data = json.loads(m.group(1))
        out = []
        for j in (data[0] if data and isinstance(data[0], list) else []):
            try:
                jid, title = str(j[0]), j[1]
                locs = [l[0] for l in (j[9] or []) if l and l[0]]
                text = " ".join((x[1] if isinstance(x, list) and len(x) > 1 and x[1] else "") for x in (j[10], j[3], j[4]))
                ts = (j[12] or [None])[0] if len(j) > 12 else None
            except (IndexError, TypeError):
                continue
            india = [l for l in locs if INDIA_WORD.search(l)]
            if not india:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            out.append(Posting(company, self.name, jid, title, " / ".join(india),
                               f"{self.URL}/{jid}-{slug}", _plain(text), str(ts or ""), posted=_date(ts)))
        return out


BIGTECH_SOURCES = {s.name: s for s in (AmazonSource(), EightfoldSource(), AppleSource(), AtlassianSource(),
                                       GoldmanSource(), OracleHCMSource(), WorkdaySource(), GoogleSource())}

# (display name, board, token, est. India fresher CTC band) — est_ctc is an ESTIMATE from public reports, not an
# offer figure (same convention as job_companies.NEXTLEET_COMPANIES); the UI must label it "est.".
BIGTECH_COMPANIES = [
    ("Amazon", "amazon", "software-development", "40-50 LPA"),
    ("Microsoft", "eightfold", "apply.careers.microsoft.com|microsoft.com", "45-55 LPA"),
    ("Qualcomm", "eightfold", "careers.qualcomm.com|qualcomm.com", "18-25 LPA"),
    ("Apple", "apple", "postLocation-INDC", "30-45 LPA"),
    ("Atlassian", "atlassian", "all", "50-65 LPA"),
    ("Goldman Sachs", "goldman", "software", "25-35 LPA"),
    ("JPMorgan Chase", "oraclehcm", "jpmc.fa.oraclecloud.com|CX_1001|300000000289360|software", "18-25 LPA"),
    ("Texas Instruments", "oraclehcm", "edbz.fa.us2.oraclecloud.com|CX|300000000361484|", "20-28 LPA"),
    ("Oracle", "oraclehcm", "eeho.fa.us2.oraclecloud.com|CX_45001|300000000106947|", "15-25 LPA"),
    ("Samsung R&D", "workday_bt", "sec|wd3|Samsung_Careers|Location_Country=c4f78be1a8f14da0ab49ce1162348a5e",
     "18-25 LPA"),
]

# Opt-in: parses a server-rendered page blob rather than a JSON endpoint (see docstring).
BIGTECH_EXTRA = [("Google", "google", "EARLY", "45-60 LPA")]
