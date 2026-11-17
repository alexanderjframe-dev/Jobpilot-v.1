"""Unit and fake-client tests for optional job providers. No live API calls."""
import asyncio
import os
import unittest
from unittest.mock import patch

from extra_job_sources import (
    adzuna_jobs, discover_more, jobicy_jobs, jsearch_jobs,
    remoteok_jobs, search_terms, usajobs_jobs,
)

class DummyResponse:
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        return None
    def json(self):
        return self.data

class FakeClient:
    def __init__(self):
        self.calls = []
    async def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        if "jobicy.com" in url:
            return DummyResponse({"jobs":[{
                "id": 11, "url":"https://jobicy.com/jobs/test-role",
                "jobTitle":"Customer Support", "companyName":"Acme",
                "jobGeo":"USA", "jobType":["full-time"],
                "jobDescription":"Support customers", "pubDate":"2026-11-16T10:00:00Z",
            }]})
        if "remoteok.com" in url:
            return DummyResponse([{"legal":"terms"},{
                "id":99, "position":"Entry-level Analyst", "company":"Acme",
                "url":"https://remoteok.com/remote-jobs/99", "location":"USA"
            }])
        if "adzuna.com" in url:
            return DummyResponse({"results":[{
                "id":31,"title":"Warehouse Associate",
                "company":{"display_name":"Warehouse Inc"},
                "location":{"display_name":"Dallas, Texas"},
                "redirect_url":"https://www.adzuna.com/details/31",
                "description":"Stock inventory",
            }]})
        if "rapidapi.com" in url:
            return DummyResponse({"data":{"jobs":[{
                "job_id":"remote-10", "job_title":"Retail Assistant",
                "employer_name":"Retail Inc", "job_publisher":"Indeed",
                "job_apply_link":"https://www.indeed.com/viewjob?jk=abc",
                "job_city":"Dallas", "job_state":"TX", "job_is_remote":False,
                "job_description":"In-store assistance"
            }]}})
        if "usajobs.gov" in url:
            return DummyResponse({"SearchResult":{"SearchResultItems":[{
                "MatchedObjectDescriptor":{
                    "PositionTitle":"Clerical Assistant","PositionID":"555",
                    "PositionURI":"https://www.usajobs.gov/job/555",
                    "OrganizationName":"US Department of Example",
                    "PositionLocationDisplay":"Dallas, TX",
                }
            }]}})
        raise AssertionError("Unexpected URL: " + url)

class NewFeedsTests(unittest.TestCase):
    def test_normalizers(self):
        self.assertEqual(jobicy_jobs({"jobs":[]}), [])
        self.assertEqual(remoteok_jobs([{"legal":"terms"}]), [])
        self.assertEqual(adzuna_jobs({"results":[]}), [])
        self.assertEqual(jsearch_jobs({"data":{"jobs":[]}}), [])
        self.assertEqual(usajobs_jobs({"SearchResult":{"SearchResultItems":[]}}), [])
        self.assertEqual(search_terms({"target_titles":"retail,warehouse,retail,IT"}), ["", "retail", "warehouse", "IT"])

    def test_free_feeds_work_without_keys(self):
        client = FakeClient()
        jobs, counts, errors = [], {}, []
        with patch.dict(os.environ, {}, clear=True):
            asyncio.run(discover_more(client, {"max_jobs_per_feed":120,"location":"Dallas, TX"}, jobs, counts, errors))
        self.assertEqual(errors, [])
        self.assertEqual([j["source"] for j in jobs], ["Jobicy", "Remote OK"])
        self.assertEqual(counts["Jobicy"],1)
        self.assertEqual(counts["Remote OK"],1)
        self.assertEqual(len(client.calls),2)

    def test_paid_local_providers_only_run_with_explicit_keys(self):
        client = FakeClient()
        jobs, counts, errors = [], {}, []
        env = {
            "ADZUNA_APP_ID":"test-id", "ADZUNA_APP_KEY":"secret-test-adzuna",
            "JSEARCH_API_KEY":"secret-test-jsearch",
            "USAJOBS_API_KEY":"secret-test-usajobs", "USAJOBS_EMAIL":"test@example.org",
        }
        with patch.dict(os.environ,env,clear=True):
            asyncio.run(discover_more(client,{
                "max_jobs_per_feed":120, "location":"Dallas, TX",
                "target_titles":"retail,warehouse"
            },jobs,counts,errors))
        self.assertEqual(errors, [])
        self.assertEqual(len(client.calls),9) # 2 public + 3 Adzuna + 3 JSearch + 1 USAJOBS
        self.assertIn("Adzuna", [j["source"] for j in jobs])
        self.assertIn("USAJOBS", [j["source"] for j in jobs])
        self.assertTrue(any(j["source"].startswith("JSearch /") for j in jobs))
        self.assertFalse(any("secret-test-" in str(j) for j in jobs))

    def test_errors_do_not_expose_keys(self):
        class FailingClient:
            async def get(self, url, params=None, headers=None):
                raise ValueError("request failed: " + str(params))
        jobs, counts, errors = [], {}, []
        with patch.dict(os.environ, {"ADZUNA_APP_ID":"abc", "ADZUNA_APP_KEY":"private-key"}, clear=True):
            asyncio.run(discover_more(FailingClient(),{
                "max_jobs_per_feed":120, "location":"Dallas, TX",
                "jobicy_enabled":False, "remoteok_enabled":False,
                "target_titles":"warehouse"
            },jobs,counts,errors))
        self.assertTrue(errors)
        self.assertTrue(all("private-key" not in error for error in errors))


if __name__ == "__main__":
    unittest.main()
