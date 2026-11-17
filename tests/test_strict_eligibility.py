"""Strict eligibility regression suite. No private profile data or live feeds."""
import unittest

from strict_eligibility import (
    parsed_area, required_education, remote_area_ok, area_reason, role_reason,
    strict_reason, EDUCATION_LEVELS
)

CFG = {
    "location":"Dallas, TX", "location_confirmed":True,
    "location_aliases":"Irving, TX; Plano, TX",
    "target_titles":"retail associate, warehouse associate, customer service, stocker, IT support",
    "max_experience_years":2,
}
PROFILE = {"education_level":"ged", "skills":"Customer service"}

def job(title, location="Dallas, TX", mode="onsite", desc="Paid training and customer service skills are provided at this location."):
    return {"title":title,"location":location,"work_mode":mode,"description":desc}

class StrictEligibilityTests(unittest.TestCase):
    def check(self,j,cfg=None,p=None):
        return strict_reason(j,CFG if cfg is None else cfg,PROFILE if p is None else p)

    def test_missing_education_requires_confirmation(self):
        self.assertIn("education",self.check(job("Retail Associate"),p={}).lower())

    def test_unconfirmed_location_blocks_even_if_matches_default(self):
        self.assertIn("Confirm",self.check(job("Retail Associate"),cfg={**CFG,"location_confirmed":False}))

    def test_city_and_state_are_required(self):
        self.assertEqual(parsed_area("Dallas, TX"),("dallas","TX"))
        self.assertEqual(parsed_area("Dallas, Texas"),("dallas","TX"))
        self.assertIsNone(parsed_area("Dallas"))
        self.assertIsNone(parsed_area("TX"))
        self.assertIsNone(parsed_area("Dallas, ZZ"))

    def test_only_selected_cities_allowed(self):
        self.assertEqual(self.check(job("Warehouse Fulfillment Associate", "Dallas, TX")), "")
        self.assertEqual(self.check(job("Warehouse Associate", "Irving, Texas")), "")
        self.assertEqual(self.check(job("Stock Clerk", "Plano, TX")), "")
        self.assertIn("outside",self.check(job("Warehouse Associate","Austin, TX")).lower())
        self.assertIn("outside",self.check(job("Warehouse Associate","Fort Worth, TX")).lower())

    def test_legacy_austin_nearby_cities_are_not_secretly_accepted(self):
        self.assertIn("outside",self.check(job("Stock Clerk", "Round Rock, TX")).lower())

    def test_remote_requires_us_or_state_specific_eligibility(self):
        self.assertEqual(self.check(job("Customer Support Agent", "USA", "remote")), "")
        self.assertEqual(self.check(job("Customer Support Agent", "United States", "remote")), "")
        self.assertEqual(self.check(job("Customer Support Agent", "Worldwide", "remote")), "")
        self.assertEqual(self.check(job("Customer Support Agent", "Texas - Remote", "remote")), "")
        self.assertIn("Remote",self.check(job("Customer Support Agent", "Remote", "remote")))
        self.assertIn("Remote",self.check(job("Customer Support Agent", "Canada only", "remote")))
        self.assertIn("Remote",self.check(job("Customer Support Agent", "California", "remote")))

    def test_remote_description_can_confirm_residency(self):
        self.assertEqual(self.check(job(
            "Customer Support Agent", "Remote", "remote",
            "Applicants must be based in the United States and provide customer support.")), "")
        self.assertEqual(self.check(job(
            "Customer Support Agent", "Remote", "remote",
            "Applicants must be based in Texas to handle customer support calls.")), "")

    def test_county_name_does_not_silently_expand_city(self):
        self.assertIn("outside",self.check(job(
            "Warehouse Associate","Dallas County, Texas")).lower())

    def test_remote_state_restrictions_override_usa(self):
        j=job("Customer Support Agent","United States","remote",
              "Remote in United States, but must be based in California.")
        self.assertIn("Remote",self.check(j))
        j=job("Customer Support Agent","USA excluding TX","remote")
        self.assertIn("Remote",self.check(j))

    def test_golden_job_matches_education_and_role_and_location(self):
        self.assertEqual(self.check(job("Retail Associate","Dallas, TX","onsite",
              "High school diploma or GED required. Customer assistance and cash handling.")),"")
        self.assertEqual(self.check(job("IT Help Desk Associate","Plano, TX","onsite",
              "Associate degree preferred. Training for junior technical support.")),"")

    def test_required_specialized_certification_is_not_assumed(self):
        j=job("IT Support Technician", "Dallas, TX", "onsite",
              "Applicants must have CompTIA A+ certification and customer support skills.")
        self.assertIn("certification",self.check(j))
        preferred=job("IT Support Technician","Dallas, TX","onsite",
              "CompTIA A+ certification preferred; training is provided for new staff.")
        self.assertEqual(self.check(preferred),"")

    def test_language_qualification_in_description_is_not_assumed(self):
        j=job("Customer Service Associate", "Dallas, TX", "onsite",
              "You must be fluent in Lao and English for live customer calls.")
        self.assertIn("fluency",self.check(j))
        preferred=job("Customer Service Associate","Dallas, TX","onsite",
              "Spanish language proficiency preferred, but not required; paid training available.")
        self.assertEqual(self.check(preferred),"")

    def test_leadership_without_manager_word_is_excluded(self):
        self.assertIn("leadership",self.check(job("Retail Shift Lead")).lower())
        self.assertIn("leadership",self.check(job("Lead Customer Support Agent")).lower())

    def test_job_titles_are_not_mistaken_for_degrees(self):
        self.assertEqual(required_education(
            "Retail associates assist customers and master the point-of-sale system."),0)
        self.assertEqual(required_education(
            "An associate cashier role with a friendly team and paid training."),0)
        self.assertEqual(required_education(
            "Associate degree in accounting is required for this job."),3)
        self.assertEqual(self.check(job("Retail Associate","Dallas, TX","onsite",
            "Associates will support customers and master daily stocking tasks.")),"")

    def test_higher_required_education_is_excluded(self):
        self.assertEqual(required_education("Requires a bachelor's degree in a related subject."),4)
        self.assertEqual(required_education("Master's degree is required."),5)
        self.assertEqual(required_education("High school diploma or GED required."),1)
        self.assertEqual(required_education("A bachelor's degree is preferred."),0)
        j=job("Customer Service Representative","Dallas, TX","onsite",
              "Applicants must have a bachelor's degree in business administration.")
        self.assertIn("above",self.check(j))
        self.assertEqual(self.check(j,p={"education_level":"bachelor"}),"")

    def test_wrong_job_categories_are_excluded(self):
        self.assertIn("target roles",self.check(job("Graphic Designer")))
        self.assertIn("Specialized",self.check(job("Cloud Solutions Architect")))
        self.assertIn("target roles",self.check(job("Territory Representative")))
        self.assertIn("Specialized",self.check(job("Research Scientist")))

    def test_manager_and_licensed_specialists_blocked(self):
        self.assertIn("Management",self.check(job("Territory Manager")))
        self.assertIn("Management",self.check(job("Store Manager")))
        self.assertIn("Management",self.check(job("Sales Supervisor")))

    def test_short_regular_listing_is_a_possible_match_not_an_auto_rejection(self):
        from strict_eligibility import review_note
        sample=job("Retail Associate",desc="")
        self.assertEqual(self.check(sample),"")
        self.assertIn("Verify",review_note(sample))

    def test_regular_jobs_do_not_need_exact_target_keywords(self):
        for title in ("Cashier", "Grocery Clerk", "Dishwasher", "Crew Member",
                      "Housekeeper", "General Laborer", "Production Associate",
                      "Janitor", "Front Desk Agent", "Shipping Clerk", "Packer"):
            with self.subTest(title=title):
                self.assertEqual(self.check(job(title)), "")
        self.assertIn("target roles",self.check(job("Dishwasher"),cfg={
            **CFG,"regular_jobs_enabled":False
        }))

    def test_engineer_role_is_not_a_regular_team_member_match(self):
        self.assertIn("Specialized",self.check(job(
            "Software Engineer - Team Member",desc=
            "Work with team members and write full-stack production software.")))
        self.assertIn("Specialized",self.check(job(
            "Sales Engineer, Customer Support",desc=
            "Provide customer support and solution architecture for enterprise customers.")))

    def test_regular_job_education_and_location_are_still_hard_limits(self):
        self.assertIn("outside",self.check(job("Cashier","Austin, TX")).lower())
        self.assertIn("above",self.check(job(
            "Cashier","Dallas, TX","onsite",
            "Bachelor's degree required. Daily payments and customer service.")))
        self.assertIn("Management",self.check(job("Warehouse Manager")))
        self.assertIn("fluency",self.check(job(
            "Customer Service Associate","Dallas, TX","onsite",
            "Must be fluent in Mandarin. Helps customers with sales and returns.")))
        self.assertIn("certification",self.check(job(
            "Warehouse Associate","Dallas, TX","onsite",
            "Must have forklift certification. Picking and packing items.")))


    def test_profile_levels_are_explicit_not_inferred(self):
        self.assertIn("ged",EDUCATION_LEVELS)
        self.assertNotIn("some experience",EDUCATION_LEVELS)
        self.assertIn("education",self.check(job("Retail Associate"),
                                            p={"education":"GED 2025"}).lower())

if __name__ == "__main__":
    unittest.main()
