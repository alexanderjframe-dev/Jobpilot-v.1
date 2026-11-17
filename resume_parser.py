"""Conservative, local resume text extraction for the editable JobPilot profile.

No network calls and no guesses for legal eligibility or sponsorship.
"""
from __future__ import annotations

from io import BytesIO
import re
import zipfile

STATES = set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.split())
EMAIL_RE = re.compile(r'(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])')
PHONE_RE = re.compile(r'(?<!\d)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]?[2-9]\d{2}[ .-]?\d{4}(?!\d)')
LINK_RE = re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w%-]+/?', re.I)
URL_RE = re.compile(r'https?://[^\s,;<>]+', re.I)
HEADINGS = {
 'summary':'summary', 'professional summary':'summary', 'career summary':'summary',
 'profile':'summary', 'professional profile':'summary', 'objective':'summary', 'career objective':'summary',
 'experience':'experience', 'work experience':'experience', 'professional experience':'experience',
 'employment history':'experience', 'work history':'experience', 'relevant experience':'experience',
 'education':'education', 'education and certifications':'education', 'academic background':'education',
 'certifications':'education', 'licenses and certifications':'education',
 'skills':'skills', 'technical skills':'skills', 'core skills':'skills', 'key skills':'skills',
 'core competencies':'skills', 'skills and abilities':'skills',
}
FIELD_MAX = {'summary':3500,'experience':5000,'education':4000,'skills':2000}


def extract_resume_text(raw: bytes, suffix: str) -> tuple[str, str]:
    """Returns (text, warning). Extraction failures do not block saving the file."""
    try:
        if suffix == '.txt':
            text = raw.decode('utf-8-sig', 'replace')
        elif suffix == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(raw), strict=False)
            if reader.is_encrypted:
                return '', 'This PDF is password protected. Save an unlocked PDF and re-upload it.'
            text = '\n'.join((page.extract_text(extraction_mode='plain') or '') for page in list(reader.pages)[:30])
        elif suffix == '.docx':
            from docx import Document
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                if len(archive.infolist()) > 1200 or sum(i.file_size for i in archive.infolist()) > 20_000_000:
                    return '', 'This DOCX is too complex to read safely. Export a PDF instead.'
            document = Document(BytesIO(raw))
            paragraphs = [p.text for p in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    paragraphs.append(' | '.join(cell.text for cell in row.cells))
            text = '\n'.join(paragraphs)
        else:
            return '', 'This file format is not supported.'
        text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\x00', '')[:140_000]
        if not text.strip():
            return '', 'No selectable text found. If this is a scanned resume, export a text-based PDF or DOCX.'
        return text, ''
    except Exception:
        return '', 'The resume was uploaded, but its text could not be read. Try exporting a fresh PDF.'


def parse_resume(text: str) -> dict[str, str]:
    """Extract only explicitly present resume facts. Never infer authorization or visa status."""
    if not text.strip():
        return {}
    lines = [re.sub(r'[\t\u00a0]+', ' ', s).strip(' \t•·') for s in text.splitlines()]
    lines = [s for s in lines if s]
    result = {}
    head = '\n'.join(lines[:25])
    email = EMAIL_RE.search(head)
    if email:
        result['email'] = email.group(0)
    phone = PHONE_RE.search(head)
    if phone:
        result['phone'] = phone.group(0)
    linkedin = LINK_RE.search(text)
    if linkedin:
        candidate = linkedin.group(0)
        result['linkedin'] = candidate if candidate.startswith('http') else 'https://' + candidate
    for url in URL_RE.findall(head):
        url = url.rstrip(').,;')
        if not re.search(r'linkedin\.com|mailto:|jobboard|indeed\.com', url, re.I):
            result['portfolio'] = url
            break
    # Only accept likely full names near the top. Never interpret a job title as a name.
    for candidate in lines[:9]:
        candidate = re.sub(r'^(?:name)\s*:\s*', '', candidate, flags=re.I)
        candidate = re.split(r'\s*[|•·]\s*', candidate)[0].strip()
        if any(ch in candidate for ch in '@:/\\0123456789') or len(candidate)>60:
            continue
        if candidate.lower().strip(' :') in HEADINGS or candidate.lower() in ('resume', 'curriculum vitae'):
            continue
        parts = candidate.split()
        if not 2 <= len(parts) <= 4:
            continue
        if not all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", p) for p in parts):
            continue
        if any(p.lower() in {'professional','software','developer','manager','customer','service','resume','assistant','associate','engineer','college','university'} for p in parts):
            continue
        result['first_name'] = parts[0]
        result['last_name'] = parts[-1]
        break
    # Only parse labelled addresses or a contact line with a valid US state abbreviation.
    for line in lines[:18]:
        if len(line) > 100:
            continue
        for segment in re.split(r'\s*[|•·]\s*', line):
            segment = re.sub(r'^\s*(?:location|address|based in|city)\s*:\s*','',segment,flags=re.I)
            match = re.search(r'\b([A-Za-z][A-Za-z .-]{1,45}?),\s*([A-Z]{2})\b(?:\s+\d{5}(?:-\d{4})?)?', segment)
            if match and match.group(2) in STATES and '@' not in match.group(1):
                city = match.group(1).strip().split('  ')[-1]
                if 1 <= len(city.split()) <= 4:
                    result['city'],result['state'] = city,match.group(2)
                    break
        if 'city' in result:
            break
    active = None
    sections: dict[str, list[str]] = {'summary':[], 'experience':[], 'education':[], 'skills':[]}
    for line in lines:
        key = re.sub(r'\s+', ' ', line.lower().strip(' :-_#')).strip()
        if key in HEADINGS:
            active = HEADINGS[key]
            continue
        # Don't indiscriminately absorb references, languages or personal details into the last section.
        if key in {'references', 'languages', 'interests', 'awards', 'projects', 'volunteer work', 'additional information'}:
            active = None
            continue
        if active:
            sections[active].append(line)
    for key, content in sections.items():
        if content:
            result[key] = '\n'.join(content)[:FIELD_MAX[key]].strip()
    # Inline skills labels also occur in compact single-column resumes.
    if not result.get('skills'):
        for line in lines[:45]:
            m = re.match(r'^(?:skills|technical skills|core competencies)\s*:\s*(.{3,2000})$',line,re.I)
            if m:
                result['skills'] = m.group(1).strip()
                break
    return {k:v for k,v in result.items() if v}
