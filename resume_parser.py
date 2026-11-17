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
 'professional overview':'summary', 'career highlights':'summary',
 'about me':'summary', 'about':'summary', 'the value i bring':'summary',
 'what i bring':'summary', 'value i bring':'summary',
 'overview':'summary', 'personal statement':'summary',
 'key strengths':'skills', 'core strengths':'skills', 'professional skills':'skills',
 'areas of expertise':'skills', 'areas of strength':'skills',
 'skills and strengths':'skills', 'skills strengths':'skills',
 'core skills strengths':'skills', 'core skills':'skills',
 'skills abilities':'skills', 'relevant skills':'skills', 'tools and skills':'skills',
 'tools and technology':'skills', 'technical proficiencies':'skills',
 'competencies':'skills', 'strengths':'skills', 'qualifications':'skills',
 'professional strengths':'skills', 'skills highlights':'skills',
}
FIELD_MAX = {'summary':3500,'experience':5000,'education':4000,'skills':2000}

# A heading such as "THE BRING" is not a person's name. Prefer leaving
# names empty over inserting a slogan into an application.
NAME_NOISE = {
 'the','a','an','my','our','your','what','who','why','how','i','we','and','of',
 'this','that','these','those','to','for','with','from','in','at','by',
 'bring','value','story','next','future','career','goal','goals','strengths',
 'skills','experience','education','summary','profile','contact',
 'work','employment','professional','employment','history','qualifications',
 'customer','service','software','developer','manager','assistant',
 'associate','engineer','sales','leadership','operations','resume',
 'curriculum','vitae','high','school','college','university','academy',
 'institute','diploma','degree','certificate','certification','team',
 'strong','results','driven','proven','reliable','independent',
}
STOP_SECTION_HEADINGS = {
 'references','languages','interests','awards','projects','volunteer work',
 'additional information','contact','contact information',
 'achievements','the skills i bring','the experience i bring','the bring',
 'personal details','portfolio','links',
}

def normalized_label(line: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', line.lower())).strip()


def explicit_skill_fallback(text: str) -> str:
    """Only use concrete skills/areas literally mentioned in the resume."""
    terms = (
        ('customer service', 'Customer service'), ('customer support', 'Customer support'),
        ('problem solving', 'Problem solving'), ('problem-solving', 'Problem solving'),
        ('communication', 'Communication'), ('time management', 'Time management'),
        ('sales', 'Sales'), ('leadership', 'Leadership'), ('operations', 'Operations'),
        ('delivery', 'Delivery'), ('deliveries', 'Deliveries'),
        ('inventory', 'Inventory'), ('data entry', 'Data entry'),
        ('cash handling', 'Cash handling'), ('scheduling', 'Scheduling'),
        ('excel', 'Excel'), ('microsoft office', 'Microsoft Office'),
        ('python', 'Python'), ('javascript', 'JavaScript'),
        ('project management', 'Project management'), ('customer updates', 'Customer updates'),
        ('point of sale', 'Point of sale'), ('pos', 'POS'),
    )
    found = []
    for phrase, label in terms:
        if re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text, re.I) and label not in found:
            found.append(label)
    return ', '.join(found[:12]) if len(found) >= 2 else ''


def experience_summary(experience: str) -> str:
    """Lightly rephrase only an explicit responsibility, never invent one."""
    lines = [line.strip(' •*-\t') for line in experience.splitlines() if line.strip()]
    for line in lines[:14]:
        if len(line) < 35 or len(line) > 210 or '@' in line or '|' in line:
            continue
        match = re.match(
            r'^(organize|manage|coordinate|provide|handle|support|deliver|process|'
            r'maintain|assist|lead|help|track|schedule|prepare|resolve|serve)\b\s+(.+)',
            line, re.I
        )
        if not match:
            continue
        gerunds = {
            'organize':'organizing','manage':'managing','coordinate':'coordinating',
            'provide':'providing','handle':'handling','support':'supporting',
            'deliver':'delivering','process':'processing','maintain':'maintaining',
            'assist':'assisting','lead':'leading','help':'helping','track':'tracking',
            'schedule':'scheduling','prepare':'preparing','resolve':'resolving',
            'serve':'serving',
        }
        action = gerunds[match.group(1).lower()]
        detail = match.group(2).rstrip(' .;')
        return ('Experience ' + action + ' ' + detail + '.')[:350]
    return ''


def plausible_name(line: str) -> list[str] | None:
    """A strictly limited candidate, not an assertion of identity."""
    candidate = re.sub(r'^name\s*:\s*', '', line.strip(), flags=re.I)
    candidate = re.split(r'\s*[|•·]\s*', candidate)[0].strip()
    if len(candidate)>60 or re.search(r'[@:/\\0-9]', candidate):
        return None
    parts = candidate.split()
    if not 2 <= len(parts) <= 3:
        return None
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]{1,24}", part) for part in parts):
        return None
    if any(part.lower().strip('.-') in NAME_NOISE for part in parts):
        return None
    return parts

def looks_like_repeated_masthead(line: str, next_line: str) -> bool:
    """Stop a section if PDF reading order has jumped to a second name/header."""
    return bool(
        line.isupper()
        and plausible_name(line)
        and (
            re.search(r'\s/\s', next_line)
            or EMAIL_RE.search(next_line)
            or PHONE_RE.search(next_line)
        )
    )



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
    # A contact name should be near the top. If the candidate looks like a
    # section title/slogan, leave the field blank for the user to review.
    if email or phone:
        for candidate in lines[:7]:
            if candidate.lower().strip(' :-_#') in HEADINGS:
                break
            parts = plausible_name(candidate)
            if parts:
                result['first_name'], result['last_name'] = parts[0], parts[-1]
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
    for index, line in enumerate(lines):
        key = normalized_label(line)
        if key in HEADINGS:
            active = HEADINGS[key]
            continue
        # Also handle "Skills: ..." and "Professional Summary: ..." on one line.
        if ':' in line:
            label, body = line.split(':', 1)
            if normalized_label(label) in HEADINGS:
                active = HEADINGS[normalized_label(label)]
                if body.strip():
                    sections[active].append(body.strip())
                continue
        # Stop when the resume changes to an unmodeled section or when text
        # extraction jumps into a repeated contact masthead/column.
        if key in STOP_SECTION_HEADINGS:
            active = None
            continue
        next_line = lines[index+1] if index+1 < len(lines) else ''
        if active and looks_like_repeated_masthead(line, next_line):
            active = None
            continue
        if active:
            sections[active].append(line)
    for key, content in sections.items():
        if content:
            result[key] = '\n'.join(content)[:FIELD_MAX[key]].strip()
    # On resumes without a conventional Skills section, look for exact
    # skill phrases explicitly mentioned outside URLs and email addresses.
    if not result.get('skills'):
        skill_source = '\n'.join(line for line in lines if '@' not in line and 'http' not in line.lower())
        derived = explicit_skill_fallback(skill_source)
        if derived:
            result['skills'] = derived
    # If no summary is printed, draft one from a stated work responsibility.
    # Never invent experience and leave the field blank when evidence is thin.
    if not result.get('summary') and result.get('experience'):
        draft = experience_summary(result['experience'])
        if draft:
            result['summary'] = draft
    return {k:v for k,v in result.items() if v}
