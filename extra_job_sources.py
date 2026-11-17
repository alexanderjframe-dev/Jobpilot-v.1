"""Additional documented job feeds; no direct scraping of job-board websites."""
from __future__ import annotations
import asyncio
import os
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

def text_only(value):
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)[:13000]

def iso(value):
    if not value:
        return None
    try:
        if isinstance(value, (float, int)):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
    except (TypeError, ValueError, OSError):
        return None

def jobicy_jobs(data):
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("Jobicy response did not contain jobs")
    jobs = []
    for x in data["jobs"]:
        if not isinstance(x, dict) or not x.get("url") or not x.get("jobTitle"):
            continue
        period = str(x.get("salaryPeriod") or "")
        lo, hi = x.get("salaryMin"), x.get("salaryMax")
        currency = str(x.get("salaryCurrency") or "")
        salary = (f"{currency} {lo}–{hi} / {period}" if lo is not None and hi is not None
                  else f"{currency} {lo} / {period}" if lo is not None else "")
        types = x.get("jobType") or []
        jobs.append({
            "source": "Jobicy", "source_id": x.get("id") or x["url"],
            "title": x["jobTitle"], "company": x.get("companyName") or "Unknown",
            "location": x.get("jobGeo") or "Remote", "work_mode": "remote",
            "employment_type": ", ".join(map(str, types)) if isinstance(types, list) else str(types),
            "description": text_only(x.get("jobDescription") or x.get("jobExcerpt")),
            "url": x["url"], "salary": salary, "posted_at": iso(x.get("pubDate")),
        })
    return jobs

def remoteok_jobs(data):
    if not isinstance(data, list):
        raise ValueError("Remote OK did not return a list")
    jobs = []
    for x in data:
        if not isinstance(x, dict) or not x.get("position") or not x.get("url"):
            continue
        jobs.append({
            "source": "Remote OK", "source_id": x.get("id") or x.get("slug") or x["url"],
            "title": x["position"], "company": x.get("company") or "Unknown",
            "location": x.get("location") or "Remote (check eligibility)",
            "work_mode": "remote", "employment_type": "",
            "description": text_only(x.get("description")),
            "url": x["url"], "salary": "", "posted_at": iso(x.get("epoch") or x.get("date")),
        })
    return jobs

def adzuna_jobs(data):
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Adzuna response did not contain results")
    jobs = []
    for x in data["results"]:
        if not isinstance(x, dict):
            continue
        url = x.get("redirect_url")
        if not url:
            continue
        loc, company = x.get("location") or {}, x.get("company") or {}
        lo, hi = x.get("salary_min"), x.get("salary_max")
        salary = (f"USD {round(lo):,}–{round(hi):,}/year"
                  if isinstance(lo, (float,int)) and isinstance(hi, (float,int)) else "")
        if salary and x.get("salary_is_predicted"):
            salary += " (estimate)"
        jobs.append({
            "source": "Adzuna", "source_id": x.get("id") or url,
            "title": x.get("title") or "Untitled",
            "company": company.get("display_name") if isinstance(company, dict) else str(company),
            "location": loc.get("display_name") if isinstance(loc, dict) else str(loc),
            "work_mode": "remote" if "remote" in str(x.get("title") or "").lower() else "onsite",
            "employment_type": x.get("contract_time") or x.get("contract_type") or "",
            "description": text_only(x.get("description")), "url": url, "salary": salary,
            "posted_at": iso(x.get("created")),
        })
    return jobs

def jsearch_jobs(data):
    payload = data.get("data") if isinstance(data, dict) else None
    if isinstance(payload, dict):
        payload = payload.get("jobs", payload.get("data"))
    if not isinstance(payload, list):
        raise ValueError("JSearch response did not contain jobs")
    jobs = []
    for x in payload:
        if not isinstance(x, dict):
            continue
        url = x.get("job_apply_link") or x.get("job_google_link")
        if not url:
            continue
        lo, hi = x.get("job_min_salary"), x.get("job_max_salary")
        period = x.get("job_salary_period") or "year"
        salary = f"{lo}–{hi} / {period}" if lo is not None and hi is not None else ""
        location = x.get("job_location") or ", ".join(y for y in (x.get("job_city"), x.get("job_state")) if y)
        jobs.append({
            "source": "JSearch / " + str(x.get("job_publisher") or "aggregated"),
            "source_id": x.get("job_id") or url, "title": x.get("job_title") or "Untitled",
            "company": x.get("employer_name") or "Unknown",
            "location": location or ("Remote" if x.get("job_is_remote") else ""),
            "work_mode": "remote" if x.get("job_is_remote") else "onsite",
            "employment_type": x.get("job_employment_type") or "",
            "description": text_only(x.get("job_description")),
            "url": url, "salary": salary, "posted_at": iso(x.get("job_posted_at_datetime_utc")),
        })
    return jobs

def usajobs_jobs(data):
    items = (((data or {}).get("SearchResult") or {}).get("SearchResultItems"))
    if not isinstance(items, list):
        raise ValueError("USAJOBS response did not contain results")
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        x = item.get("MatchedObjectDescriptor") or {}
        title = x.get("PositionTitle")
        if not title:
            continue
        uri = x.get("PositionURI") or ""
        if not uri and x.get("PositionID"):
            uri = "https://www.usajobs.gov/job/" + str(x["PositionID"])
        if not uri:
            continue
        loc = x.get("PositionLocationDisplay") or ""
        details = (x.get("UserArea") or {}).get("Details") or {}
        jobs.append({
            "source": "USAJOBS", "source_id": x.get("PositionID") or uri,
            "title": title, "company": x.get("OrganizationName") or x.get("DepartmentName") or "US Federal Government",
            "location": loc, "work_mode": "remote" if "remote" in loc.lower() else "onsite",
            "employment_type": "", "description": text_only(details.get("JobSummary") or x.get("QualificationSummary")),
            "url": uri, "salary": "", "posted_at": iso(x.get("PublicationStartDate")),
        })
    return jobs

def search_terms(cfg):
    titles = [x.strip() for x in re.split(r"[,;\n]", str(cfg.get("target_titles") or "")) if x.strip()]
    terms = [""]
    for title in titles:
        if title.casefold() not in [t.casefold() for t in terms]:
            terms.append(title[:70])
        if len(terms) >= 4:
            break
    return terms

async def discover_more(client, cfg, items, counts, errors):
    """Append normalized listings and report source errors without failing the whole scan."""
    cap = max(10, min(250, int(cfg.get("max_jobs_per_feed") or 120)))
    async def pull(name, url, parser, *, params=None, headers=None, limit=None):
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            result = parser(response.json())
            if not isinstance(result, list):
                raise ValueError("provider did not return a list")
            selected = result[:limit or cap]
            items.extend(selected)
            counts[name] = len(selected)
        except Exception as exc:
            counts[name] = 0
            # HTTP exceptions may embed API keys in request URLs. Never send
            # provider credentials back to the browser through scan errors.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            errors.append(f"{name}: HTTP {status}" if status else f"{name}: {type(exc).__name__}")

    public_requests = []
    if cfg.get("jobicy_enabled", True):
        public_requests.append(pull("Jobicy", "https://jobicy.com/api/jobs", jobicy_jobs,
                                    params={"count": min(200, cap), "geo": "usa"}))
    if cfg.get("remoteok_enabled", True):
        public_requests.append(pull("Remote OK", "https://remoteok.com/api", remoteok_jobs))
    if public_requests:
        await asyncio.gather(*public_requests)

    location = str(cfg.get("location") or "").strip()[:120]
    adzuna_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    adzuna_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if cfg.get("adzuna_enabled", True) and adzuna_id and adzuna_key:
        for term in search_terms(cfg):
            label = "Adzuna: " + (term or "all jobs")
            params = {"app_id": adzuna_id, "app_key": adzuna_key,
                      "results_per_page": min(50, cap), "sort_by": "date"}
            if location:
                params["where"] = location
            if term:
                params["what"] = term
            await pull(label, "https://api.adzuna.com/v1/api/jobs/us/search/1",
                       adzuna_jobs, params=params)

    jsearch_key = os.environ.get("JSEARCH_API_KEY", "").strip()
    if cfg.get("jsearch_enabled", True) and jsearch_key:
        for term in search_terms(cfg)[:3]:
            title = (term + " jobs" if term else "jobs")
            query = title + (" in " + location if location else " in United States")
            await pull("JSearch: " + (term or "all jobs"),
                       "https://jsearch.p.rapidapi.com/search-v2", jsearch_jobs,
                       params={"query": query, "page": 1, "num_pages": 1, "country": "us"},
                       headers={"X-RapidAPI-Key": jsearch_key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
                       limit=30)

    usajobs_key = os.environ.get("USAJOBS_API_KEY", "").strip()
    usajobs_email = os.environ.get("USAJOBS_EMAIL", "").strip()
    if cfg.get("usajobs_enabled", True) and usajobs_key and usajobs_email:
        params = {"ResultsPerPage": min(100, cap), "Page": 1}
        if location:
            params["LocationName"] = location
        await pull("USAJOBS", "https://data.usajobs.gov/api/search", usajobs_jobs,
                   params=params, headers={"User-Agent": usajobs_email, "Authorization-Key": usajobs_key})
