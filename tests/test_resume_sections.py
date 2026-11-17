"""Regression tests for alternate resume headings and grounded autofill."""
import unittest
from resume_parser import parse_resume


class ResumeSectionsTests(unittest.TestCase):
    def test_alternate_headings(self):
        resume = """Jordan Avery
jordan@example.org
What I Bring
Known for customer communication and punctuality.
Work Experience
Independent Driver
Organize packages and customer updates reliably.
Core Skills & Strengths
Customer service, Sales, Leadership
Education
GED 2025"""
        values = parse_resume(resume)
        self.assertEqual(values['summary'], 'Known for customer communication and punctuality.')
        self.assertEqual(values['skills'], 'Customer service, Sales, Leadership')
        self.assertIn('Organize packages', values['experience'])
        self.assertNotIn('Core Skills', values['experience'])

    def test_inline_labels(self):
        resume = """Jordan Avery
jordan@example.org
Professional Summary: Friendly customer service representative.
Skills: Excel, communication, scheduling
Education: GED Completed 2025"""
        values = parse_resume(resume)
        self.assertEqual(values['summary'], 'Friendly customer service representative.')
        self.assertEqual(values['skills'], 'Excel, communication, scheduling')
        self.assertEqual(values['education'], 'GED Completed 2025')

    def test_grounded_fallback_for_unconventional_resume(self):
        resume = """THE BRING
contact@example.org
Education
GED | Completed 2025
ALEX FRAME
SALES / LEADERSHIP / OPERATIONS
12-HOUR SHIFTS
Work Experience
INDEPENDENT DELIVERY DRIVER JUN 4, 2026 - PRESENT
DoorDash | Independent Contractor
Organize time-sensitive pickups, routes, deliveries, and customer updates without direct supervision."""
        values = parse_resume(resume)
        self.assertEqual(values['education'], 'GED | Completed 2025')
        self.assertNotIn('first_name', values)
        self.assertIn('Sales', values['skills'])
        self.assertIn('Leadership', values['skills'])
        self.assertIn('Experience organizing', values['summary'])

    def test_no_unfounded_summary_or_skills(self):
        values = parse_resume('Jordan Avery\njordan@example.org\nEducation\nGED 2025')
        self.assertNotIn('summary', values)
        self.assertNotIn('skills', values)
        self.assertNotIn('work_authorized', values)
        self.assertNotIn('sponsorship', values)


if __name__ == '__main__':
    unittest.main()
