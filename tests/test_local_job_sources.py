"""No-key local job provider tests with in-memory fake responses only."""
import asyncio
import unittest

from local_job_sources import API_URL, PROVIDER, as_jobs, discover_local, search_plan
from strict_eligibility import strict_reason

CFG = {
    "location":"Dallas, TX",
    "location_confirmed":True,
    "regular_jobs_enabled":True,
    "target_titles":"retail associate, warehouse associate, customer service, stocker, IT support",
    "max_experience_years":2,
}
PROFILE = {"education_level":"ged"}

def provider_record(title,uid=1,edu=None,years=None,desc="Paid training and retail store work."):
    return {
        "job_id":uid,"title":title,"employer":"Sample Retail Corporation",
        "location":"Dallas, TX","state":"TX","apply_url":f"https://example.org/careers/{uid}",
        "description":desc,"pay_as_posted":"$18/hour","posted_at":"2026-11-17T10:00:00Z",
        "remote":False,"req_edu_level":edu,"req_hard_years":years,
    }

class DummyResponse:
    def __init__(self,payload,status=200):
        self.payload=payload
        self.status_code=status
    def raise_for_status(self):
        if self.status_code>=400:
            raise ValueError("HTTP "+str(self.status_code))
    def json(self):
        return self.payload

class FakeClient:
    def __init__(self,payload,status=200):
        self.payload=payload
        self.status=status
        self.calls=[]
    async def get(self,url,params=None,timeout=None):
        self.calls.append((url,params,timeout))
        return DummyResponse(self.payload,self.status)

class LiveLocalProviderTests(unittest.TestCase):
    def test_search_plan_is_bounded_and_only_uses_confirmed_job_preferences(self):
        plan=search_plan(CFG)
        self.assertLessEqual(len(plan),5)
        self.assertIn("cashier",plan)
        self.assertIn("warehouse",plan)
        self.assertIn("crew member",plan)
        self.assertEqual(search_plan({**CFG,"regular_jobs_enabled":False,"target_titles":"warehouse;customer support"}),["warehouse","customer support"])

    def test_uses_verified_city_and_deduplicates_original_employer_links(self):
        client=FakeClient({"jobs":[provider_record("Cashier",uid=4)]})
        items,counts,errors=[],{},[]
        self.assertTrue(asyncio.run(discover_local(client,CFG,items,counts,errors)))
        self.assertEqual(errors,[])
        self.assertEqual(counts[PROVIDER],1)  # one job repeated in each query
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["source"],PROVIDER)
        self.assertEqual(items[0]["url"],"https://example.org/careers/4")
        self.assertEqual(items[0]["salary"],"$18/hour")
        self.assertEqual(strict_reason(items[0],CFG,PROFILE),"")
        self.assertTrue(all(url==API_URL and p["where"]=="Dallas, TX" for url,p,_ in client.calls))
        self.assertTrue(all(p["radius_miles"]==25 for _,p,_ in client.calls))

    def test_provider_city_and_state_fields_are_combined_for_exact_matching(self):
        row=provider_record("Stock Clerk",uid=11)
        row["location"]="Dallas"
        normalized=as_jobs({"jobs":[row]})[0]
        self.assertEqual(normalized["location"],"Dallas, TX")
        self.assertEqual(strict_reason(normalized,CFG,PROFILE),"")
        remote=provider_record("Customer Support Agent",uid=12)
        remote["location"]="Remote"
        remote["remote"]=True
        normalized_remote=as_jobs({"jobs":[remote]})[0]
        self.assertEqual(normalized_remote["location"],"Remote")
        self.assertIn("Remote",strict_reason(normalized_remote,CFG,PROFILE))

    def test_filters_requirements_from_structured_provider_fields(self):
        jobs=as_jobs({"jobs":[
            provider_record("Cashier",uid=1,edu="bachelor",desc="Help shoppers and collect payments."),
            provider_record("Warehouse Associate",uid=2,years=5,desc="Packing orders."),
            provider_record("Territory Manager",uid=3),
            provider_record("Crew Member",uid=4,desc="Paid training.")
        ]})
        self.assertEqual(len(jobs),4)
        self.assertIn("degree required",jobs[0]["description"])
        self.assertIn("5 years",jobs[1]["description"])
        self.assertIn("above",strict_reason(jobs[0],CFG,PROFILE))
        self.assertIn("years",strict_reason(jobs[1],CFG,PROFILE,lambda j,c:
            "Listing mentions 5 years of experience; limit is 2"))
        self.assertIn("Management",strict_reason(jobs[2],CFG,PROFILE))
        self.assertEqual(strict_reason(jobs[3],CFG,PROFILE),"")

    def test_malformed_payload_is_not_treated_as_zero_jobs(self):
        with self.assertRaises(ValueError):
            as_jobs({"not_jobs":[]})
        with self.assertRaises(ValueError):
            as_jobs([])
        self.assertEqual(as_jobs({"jobs":[{"title":"No apply link"}]}),[])

    def test_missing_area_sends_no_requests(self):
        client=FakeClient({"jobs":[provider_record("Cashier")]})
        rows,counts,errors=[],{},[]
        self.assertFalse(asyncio.run(discover_local(client,{**CFG,"location_confirmed":False},rows,counts,errors)))
        self.assertEqual(client.calls,[])
        self.assertEqual(counts[PROVIDER],0)

    def test_http_429_keeps_error_visible(self):
        client=FakeClient({"error":"rate_limited"},status=429)
        jobs,counts,errors=[],{},[]
        self.assertFalse(asyncio.run(discover_local(client,CFG,jobs,counts,errors)))
        self.assertEqual(jobs,[])
        self.assertEqual(counts[PROVIDER],0)
        self.assertTrue(errors)
        self.assertTrue(all("rate limited" in m for m in errors))

if __name__ == "__main__":
    unittest.main()
