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

    def test_enterprise_sales_engineer_from_jobicy_is_hidden(self):
        cfg = dict(self.server.DEFAULTS)
        job = {
            "title":"Sales Engineer, Enterprise",
            "company":"Socket",
            "location":"USA",
            "work_mode":"remote",
            "min_hourly":92,
            "description": (
                "Required: 7 plus years of pre-sales experience in a "
                "Sales Engineering or Solutions Engineering role. "
                "Hands-on experience with enterprise cybersecurity customers."
            ),
        }
        warning = self.server.qualification_note(job,cfg)
        self.assertIn("Enterprise-level",warning)
        self.assertEqual(
            self.server.EXP_YEARS_RE.search(job["description"]).group(1),"7"
        )
        score,reasons,_ = self.server.score_job(job,cfg,dict(self.server.PROFILE_DEFAULTS))
        self.assertLessEqual(score,30)
        self.assertTrue(any("Enterprise" in text for text in reasons))

    def test_written_plus_years_is_recognized_without_enterprise_title(self):
        cfg=dict(self.server.DEFAULTS)
        job={"title":"Customer Support Specialist",
             "description":"Required: 7 plus years of customer service experience."}
        self.assertIn("7 years",self.server.qualification_note(job,cfg))

    def test_misspelled_lao_interpreter_is_a_specialist_not_a_normal_match(self):
        """Regression for the real listing title, including source typos."""
        cfg=dict(self.server.DEFAULTS)
        job={
            "title":"Internatioal Audio/Video Remote Lao/Loatian Interpreter",
            "location":"USA",
            "work_mode":"remote",
            "description":"Provide remote language interpretation for Lao and English speakers.",
            "salary":"USD 20/hour",
        }
        note=self.server.qualification_note(job,cfg)
        self.assertIn("proficiency",note)
        score,reasons,_=self.server.score_job(job,cfg,dict(self.server.PROFILE_DEFAULTS))
        self.assertLessEqual(score,30)
        self.assertTrue(any("proficiency" in reason for reason in reasons))

    def test_other_language_titles_require_proficiency_check(self):
        cfg=dict(self.server.DEFAULTS)
        for title in ("Spanish Interpreter", "Japanese-English Translator",
                      "Multilingual Customer Service Representative",
                      "Bilingual Sales Associate", "Language Interpreter (Lao)"):
            with self.subTest(title=title):
                note=self.server.qualification_note({"title":title,"description":""},cfg)
                self.assertTrue(note, title)

    def test_license_roles_flagged_but_regular_entry_level_jobs_remain(self):
        cfg=dict(self.server.DEFAULTS)
        for title in ("Registered Nurse", "Licensed Practical Nurse",
                      "CDL-A Truck Driver", "Licensed Electrician", "Attorney"):
            with self.subTest(title=title):
                self.assertIn("license",self.server.qualification_note(
                    {"title":title,"description":""},cfg))
        for title in ("Warehouse Associate", "Customer Support Agent",
                      "Entry Level IT Support", "Delivery Driver",
                      "Retail Sales Associate", "Assistant Store Manager"):
            with self.subTest(title=title):
                self.assertFalse(self.server.qualification_note(
                    {"title":title,"description":"Paid training provided."},cfg))

    def test_api_hides_interpreter_by_default_and_reveals_on_demand(self):
        job={
            "company":"Test Language Staffing","title":"Remote Lao Interpreter",
            "location":"USA","url":"https://example.org/lao-remote-interpreter",
            "description":"Fluent Lao and English interpretation required."
        }
        res=self.client.post("/api/jobs/manual",json=job)
        self.assertEqual(res.status_code,200,res.text)
        normal=self.client.get("/api/jobs").json()
        self.assertFalse(any(j["title"]==job["title"] for j in normal["jobs"]))
        self.assertGreaterEqual(normal["hidden_advanced"],1)
        all_jobs=self.client.get("/api/jobs?include_advanced=true").json()["jobs"]
        flagged=next(j for j in all_jobs if j["title"]==job["title"])
        self.assertTrue(flagged["advanced"])
        self.assertLessEqual(flagged["score"],30)

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
