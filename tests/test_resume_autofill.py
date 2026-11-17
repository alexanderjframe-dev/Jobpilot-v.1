"""Checks for conservative resume extraction and applicant profile autofill."""
import importlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from docx import Document
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from resume_parser import extract_resume_text, parse_resume

SAMPLE = """Jordan Avery
Austin, TX | (512) 555-0144 | jordan@example.com
https://linkedin.com/in/jordan-avery

Professional Summary
Reliable customer service professional.

Work Experience
Customer Service Representative - Example Co. (2023-2025)
Helped customers and processed returns.

Education
Example High School diploma

Skills
Inventory, POS, customer service
"""


class ResumeAutofillTests(unittest.TestCase):
    def test_text_parses_only_factual_fields(self):
        values = parse_resume(SAMPLE)
        self.assertEqual(values['first_name'], 'Jordan')
        self.assertEqual(values['last_name'], 'Avery')
        self.assertEqual(values['email'], 'jordan@example.com')
        self.assertEqual(values['city'], 'Austin')
        self.assertEqual(values['state'], 'TX')
        self.assertIn('processed returns', values['experience'])
        self.assertNotIn('work_authorized', values)
        self.assertNotIn('sponsorship', values)

    def test_docx_parses(self):
        document = Document()
        for line in SAMPLE.splitlines():
            document.add_paragraph(line)
        data = io.BytesIO()
        document.save(data)
        text, warning = extract_resume_text(data.getvalue(), '.docx')
        self.assertFalse(warning)
        self.assertEqual(parse_resume(text)['email'], 'jordan@example.com')

    def test_scanned_pdf_does_not_invent_details(self):
        pdf = PdfWriter()
        pdf.add_blank_page(width=612, height=792)
        data = io.BytesIO()
        pdf.write(data)
        text, warning = extract_resume_text(data.getvalue(), '.pdf')
        self.assertEqual(text, '')
        self.assertIn('No selectable text', warning)

    def test_upload_fills_blanks_but_preserves_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            old = os.environ.get('JOBPILOT_DATA_DIR')
            try:
                os.environ['JOBPILOT_DATA_DIR'] = directory
                sys.modules.pop('app', None)
                server = importlib.import_module('app')
                client = TestClient(server.app)
                client.put('/api/profile', json={'values': {
                    'first_name':'Already entered', 'work_authorized':'no'
                }})
                result = client.post('/api/resume', files={'file': (
                    'resume.txt', SAMPLE.encode(), 'text/plain'
                )})
                self.assertEqual(result.status_code, 200)
                self.assertIn('email', result.json()['autofill']['filled'])
                self.assertNotIn('first_name', result.json()['autofill']['filled'])
                profile = client.get('/api/bootstrap').json()['profile']
                self.assertEqual(profile['first_name'], 'Already entered')
                self.assertEqual(profile['last_name'], 'Avery')
                self.assertEqual(profile['work_authorized'], 'no')
                self.assertEqual(profile['email'], 'jordan@example.com')
            finally:
                if old is None:
                    os.environ.pop('JOBPILOT_DATA_DIR', None)
                else:
                    os.environ['JOBPILOT_DATA_DIR'] = old


if __name__ == '__main__':
    unittest.main()
