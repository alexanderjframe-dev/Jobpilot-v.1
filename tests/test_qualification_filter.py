"""Qualification matching regression tests. Run: python -m unittest discover -s tests -v"""
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

class QualificationMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.previous = os.environ.get("JOBPILOT_DATA_DIR")
        os.environ["JOBPILOT_DATA_DIR"] = cls.tmp.name
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        sys.modules.pop("app", None)
        cls.server = importlib.import_module("app")
        cls.client = TestClient(cls.server.app)

    @classmethod
    def tearDownClass(cls):
        if cls.previous is None:
            os.environ.pop("JOBPILOT_DATA_DIR", None)
        else:
            os.environ["JOBPILOT_DATA_DIR"] = cls.previous
        cls.tmp.cleanup()

    def test_tech_lead_is_not_an_entry_level_match(self):
        cfg = dict(self.server.DEFAULTS)
        job = {
            "title":"Tech Lead Full-Stack Rails Engineer",
            "company":"Mitre Media",
            "salary":"$170k - $200k",
            "min_hourly":90,
            "work_mode":"remote",
            "location":"USA, Canada, USA timezones",
            "description":"Lead the Rails application and support engineers"
        }
        self.assertIn("Senior", self.server.qualification_note(job,cfg))
        score, reasons, metrics = self.server.score_job(job,cfg,dict(self.server.PROFILE_DEFAULTS))
        self.assertLessEqual(score,30)
        self.assertTrue(any("Senior" in reason for reason in reasons))

    def test_higher_required_experience_is_flagged(self):
        cfg = dict(self.server.DEFAULTS)
        job = {"title":"Customer Service Representative",
               "description":"Requirements: at least 5 years of customer service experience."}
        self.assertIn("5 years", self.server.qualification_note(job,cfg))
        job["description"] = "2 years of customer service experience."
        self.assertFalse(self.server.qualification_note(job,cfg))

    def test_optional_preferred_years_are_not_hard_blocked(self):
        cfg = dict(self.server.DEFAULTS)
        job = {"title":"Retail Assistant",
               "description":"5+ years of customer service experience preferred."}
        self.assertFalse(self.server.qualification_note(job,cfg))

    def test_entry_roles_and_shift_leads_are_not_excluded(self):
        cfg = dict(self.server.DEFAULTS)
        for title in ["Junior IT Help Desk", "Warehouse Associate",
                      "Customer Support Agent", "Retail Shift Lead"]:
            with self.subTest(title=title):
                self.assertFalse(self.server.qualification_note(
                    {"title":title,"description":"Paid training provided."},cfg))

    def test_api_hides_unsuitable_but_can_reveal_them(self):
        base = {
            "company":"Test JobPilot Org",
            "location":"Austin, TX",
            "description":"Paid training",
        }
        for name,url in [
            ("Junior Customer Support Agent","https://example.org/junior-qual-test"),
            ("Tech Lead Full-Stack Rails Engineer","https://example.org/advanced-qual-test"),
        ]:
            response = self.client.post("/api/jobs/manual",json={
                **base,"title":name,"url":url
            })
            self.assertEqual(response.status_code,200,response.text)
        normal=self.client.get("/api/jobs")
        self.assertEqual(normal.status_code,200)
        self.assertEqual(normal.json()["hidden_advanced"],1)
        self.assertEqual(len(normal.json()["jobs"]),1)
        full=self.client.get("/api/jobs?include_advanced=true")
        self.assertEqual(len(full.json()["jobs"]),2)
        advanced=next(j for j in full.json()["jobs"] if j["advanced"])
        self.assertIn("leadership",advanced["qualification_note"])
        self.assertLessEqual(advanced["score"],30)
        # Preserve a user's manually saved jobs in the pipeline.
        response=self.client.patch("/api/jobs/"+advanced["id"],json={"status":"saved"})
        self.assertEqual(response.status_code,200)
        normal_again=self.client.get("/api/jobs")
        self.assertEqual(len(normal_again.json()["jobs"]),2)
        self.assertTrue(any(j["advanced"] and j["status"]=="saved" for j in normal_again.json()["jobs"]))


if __name__ == "__main__":
    unittest.main()
