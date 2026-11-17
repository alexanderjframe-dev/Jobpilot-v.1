"""No-key, city-scoped US career-site job searches.

VeritaHire documents https://veritahire.com/api/jobs-search.php as a public
search endpoint with a 30-search/hour/IP limit and up to 25 results per page.
Results are employer-site postings as represented by this independent service;
JobPilot cannot separately verify the provider's claims.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from html import unescape

from bs4 import BeautifulSoup
from strict_eligibility import parsed_area

API_URL = "https://veritahire.com/api/jobs-search.php"
PROVIDER = "VeritaHire local"
DEFAULT_TERMS = ("cashier", "warehouse", "customer service", "crew member", "stocker")
MAX_TERMS = 5

def search_plan(cfg):
    """4-5 deliberately broad searches to respect a shared server IP's rate limit."""
    titles = [x.strip().lower() for x in re.split(r"[,;\n]", str(cfg.get("target_titles") or "")) if x.strip()]
    if cfg.get("regular_jobs_enabled", True):
        terms = list(DEFAULT_TERMS)
        # Swap the final broad term for one role the user actually requested,
        # if it is not already represented (e.g. IT support, delivery).
        for name in titles:
            if name in {"entry level", "entry-level", "any", "all jobs"}:
                continue
            if name and not any(name in term or term in name for term in terms):
                terms[-1] = name[:70]
                break
    else:
        terms = [x for x in titles if x not in {"entry level", "entry-level", "any", "all jobs"}]
        if not terms:
            terms = ["entry level"]
    return list(dict.fromkeys(terms))[:MAX_TERMS]

def as_text(value,limit=11000):
    return BeautifulSoup(unescape(str(value or "")), "html.parser").get_text(" ",strip=True)[:limit]

def as_date(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value,(int,float)):
            return datetime.fromtimestamp(value,timezone.utc).isoformat()
        return datetime.fromisoformat(str(value).replace("Z","+00:00")).isoformat()
    except (ValueError,OverflowError,TypeError,OSError):
        return None

def normalized_education(value):
    if not value:
        return ""
    value=str(value).lower().replace("_"," ").strip()
    if re.search(r"\b(?:phd|doctorate|doctoral)\b",value):
        return "Doctorate degree required"
    if re.search(r"\bmaster\b",value):
        return "Master's degree required"
    if re.search(r"\bbachelor\b",value):
        return "Bachelor's degree required"
    if re.search(r"\bassociate\b",value):
        return "Associate degree required"
    if re.search(r"\b(?:high school|ged|diploma)\b",value):
        return "High school diploma or GED required"
    return ""

def as_jobs(data):
    """Validate the provider response and normalize to JobPilot's existing schema."""
    if not isinstance(data,dict) or not isinstance(data.get("jobs"),list):
        raise ValueError("Provider response did not include a jobs array")
    result=[]
    for x in data["jobs"]:
        if not isinstance(x,dict):
            continue
        url=str(x.get("apply_url") or "").strip()
        title=str(x.get("title") or "").strip()
        if not title or not url.startswith(("https://","http://")):
            continue
        location=str(x.get("location") or "").strip()
        if not location and x.get("city") and x.get("state"):
            location=f"{x['city']}, {x['state']}"
        description=as_text(x.get("description") or x.get("job_description") or x.get("snippet"))
        requirements=[]
        edu=normalized_education(x.get("req_edu_level"))
        if edu and edu.casefold() not in description.casefold():
            requirements.append(edu)
        years=x.get("req_hard_years")
        try:
            years=int(years) if years is not None and str(years).strip() else 0
        except (TypeError,ValueError):
            years=0
        if 0 < years <= 30:
            requirements.append(f"Minimum {years} years of experience required.")
        licenses=x.get("req_license_types") or []
        if isinstance(licenses,str):
            licenses=[licenses]
        if isinstance(licenses,list):
            for lic in licenses[:5]:
                lic=as_text(lic,120)
                if lic:
                    requirements.append("Mandatory license required: "+lic)
        if requirements:
            description=(description+" \n"+". ".join(requirements)).strip()
        result.append({
            "source":PROVIDER,
            "source_id":str(x.get("job_id") or x.get("id") or url),
            "title":title[:200],
            "company":str(x.get("employer") or x.get("company") or "Unknown")[:200],
            "location":location[:200],
            "work_mode":"remote" if x.get("remote") is True else "onsite",
            "employment_type":str(x.get("employment_type") or "")[:80],
            "description":description[:13000],
            "url":url,
            "salary":as_text(x.get("pay_as_posted") or x.get("pay_text"),120),
            "posted_at":as_date(x.get("posted_at") or x.get("first_seen_at")),
        })
    return result

async def discover_local(client,cfg,items,counts,errors):
    """Fetch a bounded set of real postings; keep failures visible and isolated."""
    if not cfg.get("veritahire_enabled", True):
        return False
    if not cfg.get("location_confirmed") or not parsed_area(cfg.get("location","")):
        counts[PROVIDER]=0
        return False
    location=str(cfg["location"]).strip()
    terms=search_plan(cfg)
    if not terms:
        counts[PROVIDER]=0
        return True

    async def search(term):
        try:
            response=await client.get(
                API_URL,
                params={"what":term,"where":location,"radius_miles":25},
                timeout=25
            )
            if response.status_code==429:
                return term,[], "rate limited; retry later"
            if response.status_code==503:
                return term,[], "temporarily busy (HTTP 503)"
            response.raise_for_status()
            data=response.json()
            return term,as_jobs(data),None
        except Exception as exc:
            code=getattr(getattr(exc,"response",None),"status_code",None)
            return term,[], f"HTTP {code}" if code else type(exc).__name__

    results=await asyncio.gather(*(search(t) for t in terms))
    found=[];successful=0
    for term,rows,error in results:
        if error:
            errors.append(f"{PROVIDER} ({term}): {error}")
        else:
            successful+=1
            found.extend(rows)
    # Local searches can overlap. Count unique employer application URLs.
    unique={}
    for record in found:
        unique.setdefault(record["url"],record)
    items.extend(unique.values())
    counts[PROVIDER]=len(unique)
    return successful==len(terms)
