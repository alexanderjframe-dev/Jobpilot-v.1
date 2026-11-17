"""Strict, conservative eligibility gate for normal JobPilot search results.

Checks verified applicant education, confirmed city/state + chosen nearby cities,
explicit remote eligibility, target job families, and listed education minimums.
No geocoding, commute assumptions, or inferred credentials.
"""
from __future__ import annotations

import re

STATE_NAMES = {
 'AL':'alabama','AK':'alaska','AZ':'arizona','AR':'arkansas','CA':'california',
 'CO':'colorado','CT':'connecticut','DE':'delaware','FL':'florida','GA':'georgia',
 'HI':'hawaii','ID':'idaho','IL':'illinois','IN':'indiana','IA':'iowa',
 'KS':'kansas','KY':'kentucky','LA':'louisiana','ME':'maine','MD':'maryland',
 'MA':'massachusetts','MI':'michigan','MN':'minnesota','MS':'mississippi',
 'MO':'missouri','MT':'montana','NE':'nebraska','NV':'nevada','NH':'new hampshire',
 'NJ':'new jersey','NM':'new mexico','NY':'new york','NC':'north carolina',
 'ND':'north dakota','OH':'ohio','OK':'oklahoma','OR':'oregon','PA':'pennsylvania',
 'RI':'rhode island','SC':'south carolina','SD':'south dakota',
 'TN':'tennessee','TX':'texas','UT':'utah','VT':'vermont','VA':'virginia',
 'WA':'washington','WV':'west virginia','WI':'wisconsin','WY':'wyoming',
 'DC':'district of columbia',
}
STATE_BY_NAME = {v:k for k,v in STATE_NAMES.items()}
EDUCATION_LEVELS = {
 'none':0, 'high_school':1, 'ged':1, 'some_college':2, 'associate':3,
 'bachelor':4, 'master':5, 'doctorate':6,
}
EDUCATION_NAMES = {
 'none':'No completed diploma',
 'high_school':'High school diploma',
 'ged':'GED or high school equivalency',
 'some_college':'Some college',
 'associate':"Associate degree",
 'bachelor':"Bachelor's degree",
 'master':"Master's degree",
 'doctorate':'Doctorate / professional degree',
}
ROLE_FAMILIES = {
 'retail':re.compile(r'\b(?:retail|cashier|sales associate|store associate|store clerk|shop assistant|sales clerk)\b',re.I),
 'warehouse':re.compile(r'\b(?:warehouse|fulfilment|fulfillment|picker|packer|package handler|distribution associate|shipping|receiving)\b',re.I),
 'service':re.compile(r'\b(?:customer service|customer support|contact cent(?:er|re)|call cent(?:er|re)|customer care|support agent|service representative|client support)\b',re.I),
 'stock':re.compile(r'\b(?:stocker|stocking|stock associate|stock clerk|inventory associate|merchandis\w*|shelf stock)\b',re.I),
 'it':re.compile(r'\b(?:it support|technical support|tech support|help desk|service desk|desktop support|support technician|computer support)\b',re.I),
 'delivery':re.compile(r'\b(?:delivery|courier|driver|package delivery)\b',re.I),
 'food':re.compile(r'\b(?:food service|restaurant|server|crew member|barista|kitchen|dishwasher|food prep)\b',re.I),
 'admin':re.compile(r'\b(?:administrative|office assistant|receptionist|data entry|clerical)\b',re.I),
}
# Match listed minimum education; "preferred" is handled separately.
DEGREE_PATTERNS = [
 (6, re.compile(r'\b(?:ph\.?d\.?|doctorate|doctoral degree|doctor of \w+)\b',re.I)),
 (5, re.compile(r"\b(?:master(?:['’]s)?\s+degree|master['’]s\b|master of (?:science|arts|business|engineering)|m\.?s\.?c?\.?\s+degree)\b",re.I)),
 (4, re.compile(r"\b(?:bachelor(?:['’]s)?\s+degree|bachelor['’]s\b|four[- ]year degree|college degree|b\.?s\.?\s+degree|b\.?a\.?\s+degree)\b",re.I)),
 (3, re.compile(r"\b(?:associate(?:['’]s)?\s+degree|associate['’]s\b|two[- ]year degree)\b",re.I)),
 (1, re.compile(r'\b(?:high school diploma|high school graduate|ged|general educational development|high school equivalency)\b',re.I)),
]
LOWER_ROLE_WORDS = {'job','jobs','work','full','time','part','level','entry','junior','associate','trainee','positions','position','remote'}
# Broad, ordinary jobs can be suitable even if the user's favorite titles
# don't mention the exact posting title. Specialized/management checks still
# run BEFORE this allowance; this is not a blanket eligibility bypass.
REGULAR_JOB_RE = re.compile(
    r'\b(?:cashier|retail|sales associate|store associate|store clerk|'
    r'warehouse|fulfill?ment|fulfilment|picker|packer|package handler|'
    r'stocker|stock(?:ing)? associate|stock clerk|shelf stock|'
    r'grocery clerk|courtesy clerk|bagger|cart attendant|'
    r'customer service|customer care|customer support|call center|call centre|'
    r'contact center|contact centre|support agent|'
    r'food service|fast food|restaurant crew|crew member|team member|'
    r'barista|dishwasher|kitchen helper|food prep|'
    r'housekeep(?:er|ing)|custodian|janitor|cleaner|'
    r'general labou?rer?|production associate|production worker|'
    r'assembly worker|assembler|manufacturing associate|'
    r'shipping clerk|receiving clerk|sortation associate|'
    r'office assistant|administrative assistant|receptionist|'
    r'front desk agent|data entry clerk|file clerk|'
    r'parking attendant|theater attendant|hotel attendant|'
    r'delivery driver|courier|package delivery|driver helper|'
    r'entry.level (?:technician|support|assistant|representative)|'
    r'help desk|service desk|desktop support|it support|'
    r'technical support)\b',
    re.I
)

PROFESSIONAL_TITLE_RE = re.compile(
    r'\b(?:software engineer|sales engineer|solutions? engineer|data engineer|'
    r'cloud engineer|platform engineer|cybersecurity engineer|security engineer|'
    r'full[\s-]?stack engineer|devops engineer|machine learning engineer|'
    r'data scientist|research scientist|solutions? architect|cloud architect|'
    r'account executive|investment banker|financial analyst|'
    r'project manager|product manager|territory manager)\b',re.I
)

def regular_job_title(title):
    """Routine work, excluding specialist titles even when words overlap."""
    title=str(title or '')
    return not PROFESSIONAL_TITLE_RE.search(title) and bool(REGULAR_JOB_RE.search(title))


MANAGEMENT_RE = re.compile(
 r'\b(?:manager|supervisor|superintendent|head of|director|executive|chief|president|'
 r'principal|team lead|shift lead|crew lead|crew leader|lead associate|'
 r'lead (?:customer|retail|warehouse|technical|it|support|sales|store|service|operations))\b',re.I)
CREDENTIAL_RE = re.compile(
 r"\b(?:cdl(?:[- ]?[ab])?|commercial driver['’]s license|driver['’]s licen[cs]e|"
 r"comp\s?tia\s?(?:a\+|security\+|network\+)|"
 r"professional licen[cs]e|active (?:rn|lpn) license|security clearance|"
 r"forklift certification|pmp certification)(?=$|\W)",re.I)
MANDATORY_RE = re.compile(r'\b(?:required|must|mandatory|need to have|you need|minimum qualification|valid|active|current)\b',re.I)
NON_ENGLISH_LANGUAGE_RE = re.compile(
 r'\b(?:spanish|french|german|lao|laotian|mandarin|cantonese|chinese|japanese|'
 r'korean|vietnamese|arabic|hindi|urdu|portuguese|russian|italian|'
 r'somali|amharic|tagalog|filipino|polish|thai|swahili|haitian creole)\b',re.I)


def parsed_area(raw):
    """Accept an explicit U.S. city and state, never a guessed state."""
    match = re.fullmatch(r"\s*([A-Za-z][A-Za-z .'-]{1,65}?)\s*,\s*([A-Za-z ]{2,26})\s*",str(raw or ''))
    if not match:
        return None
    city = re.sub(r'\s+', ' ',match.group(1).strip()).casefold()
    state = match.group(2).strip().upper()
    if state not in STATE_NAMES:
        state = STATE_BY_NAME.get(state.casefold(),'')
    if not state:
        return None
    return city,state

def required_education(description):
    """Return the highest visibly stated minimum; ignore clearly preferred degrees."""
    text=str(description or '')[:13000]
    levels=[]
    for rank,pattern in DEGREE_PATTERNS:
        for match in pattern.finditer(text):
            # Preference qualifiers near degree statements should not act as requirements.
            tail=text[match.end():match.end()+60].split('.')[0].split('\n')[0]
            lead=text[max(0,match.start()-25):match.start()].split('.')[-1]
            fragment=(lead+' '+tail).lower()
            preferred=bool(re.search(r'\b(?:preferred|a plus|desirable|bonus|nice to have|not required|optional)\b',fragment))
            explicit_required=bool(re.search(r'\b(?:required|mandatory|must have|minimum|at least)\b',fragment))
            if preferred and not explicit_required:
                continue
            levels.append(rank)
    return max(levels,default=0)

def remote_area_ok(location,description,applicant_state):
    loc=str(location or '').strip()
    desc=str(description or '')[:3500]
    context=(loc+' '+desc).lower()
    state_full=STATE_NAMES[applicant_state]
    user_state=r'(?:'+re.escape(applicant_state)+r'|'+re.escape(state_full)+r')'
    # Explicit exclusions take priority over a broad "US" label.
    if re.search(r'\b(?:except|excluding|excludes|not available in|not hiring in|not in|unavailable in)\s+(?:the state of\s+)?'+user_state+r'\b',context,re.I):
        return False
    if re.search(r'\b'+user_state+r'\s+(?:excluded|not eligible)\b',context,re.I):
        return False
    # If a required residence state is named and does not match, reject.
    residence=re.search(
        r'\b(?:must (?:live|reside|be based)|required to (?:live|reside|be based)|'
        r'candidates? (?:must be|based|located)|residents? (?:of|in)|'
        r'only (?:in|from)|remote (?:only )?(?:in|from))\s+'
        r'(?:in\s+|of\s+)?(?:the\s+)?([A-Za-z ]{2,26}|[A-Z]{2})\b',
        loc+' '+desc[:1500],re.I)
    if residence:
        raw=residence.group(1).strip().lower()
        region=raw.split(' ')[0]
        state_match=STATE_BY_NAME.get(raw) or (raw.upper() if raw.upper() in STATE_NAMES else '')
        if not state_match:
            for state_id,name in STATE_NAMES.items():
                if re.match(r'^'+re.escape(name)+r'\b',raw):
                    state_match=state_id
                    break
        if state_match and state_match!=applicant_state:
            return False
        if state_match==applicant_state:
            return True  # Explicit candidate residency requirement matches the user.
    positive=re.search(r'\b(?:united states|u\.?s\.?a\.?|u\.?s\.?[- ]based|nationwide|anywhere|worldwide|global|any location)\b',loc,re.I)
    if positive:
        return True
    # Some sites publish only "Remote" in location but confirm U.S. eligibility
    # in the actual description instead.
    if re.search(
        r'\b(?:candidates?|applicants?|residents?|employees?|remote workers?)'
        r'\b.{0,75}\b(?:united states|u\.?s\.?a\.?|u\.?s\.?[- ]based)\b',
        desc[:2000],re.I
    ) or re.search(
        r'\b(?:must|need to|required to)\s+(?:be\s+)?(?:based|located|reside|live)'
        r'\s+(?:in\s+)?(?:the\s+)?(?:united states|u\.?s\.?a\.?)\b',
        desc[:2000],re.I
    ):
        return True
    # Some listings explicitly restrict to a single U.S. state.
    for state_id,name in STATE_NAMES.items():
        if state_id==applicant_state:
            continue
        if re.search(r'\b(?:remote|residents?|based|only)\s+(?:in\s+)?'+re.escape(name)+r'\b',loc,re.I):
            return False
    return bool(re.search(r'\b'+user_state+r'\b',loc,re.I))

def area_reason(job,cfg):
    if not cfg.get('location_confirmed'):
        return 'Confirm your exact city and state in Preferences before trusting location matches'
    base=parsed_area(cfg.get('location',''))
    if not base:
        return 'Set a valid search location such as Dallas, TX in Preferences'
    location=str(job.get('location') or '').strip()
    if not location:
        return 'Job did not publish a location; cannot verify your search area'
    if str(job.get('work_mode') or '').lower()=='remote':
        if remote_area_ok(location,job.get('description',''),base[1]):
            return ''
        return 'Remote listing does not verify eligibility for your selected state'
    chosen=[base]
    for alias in re.split(r'[;\n]',str(cfg.get('location_aliases') or '')):
        area=parsed_area(alias)
        if area and area not in chosen:
            chosen.append(area)
    for city,state in chosen:
        state_label=STATE_NAMES[state]
        city_re=r'^(?:greater\s+)?'+re.escape(city)+r'(?:\s*,|\s+metropolitan\s+area\s*,)'
        if re.search(city_re,location,re.I) and re.search(
                r'\b(?:'+re.escape(state)+r'|'+re.escape(state_label)+r')\b',location,re.I):
            return ''
    return 'Job location is outside your selected city and nearby-city list'

def role_reason(job,cfg):
    title=str(job.get('title') or '').lower()
    targets=[s.strip().lower() for s in re.split(r'[,;\n]',str(cfg.get('target_titles') or '')) if s.strip()]
    # The user asked for ordinary jobs, not only their named favorite roles.
    # A specific preference can still be applied by disabling this toggle.
    if cfg.get('regular_jobs_enabled',True) and regular_job_title(title):
        return ''
    if not targets:
        return 'Select target job titles in Preferences'
    for target in targets:
        if target in {'entry level','entry-level','jobs','any','all jobs'}:
            continue
        if target in title:
            return ''
        for family,pattern in ROLE_FAMILIES.items():
            if pattern.search(target) and pattern.search(title):
                return ''
        words={w for w in re.findall(r'[a-z0-9]+',target) if w not in LOWER_ROLE_WORDS}
        title_words=set(re.findall(r'[a-z0-9]+',title))
        if words and words.issubset(title_words):
            return ''
    return 'Job title does not match the target roles you selected'

def strict_reason(job,cfg,profile,qualification_note=None):
    """Return first reason a job is not a strict recommendation, else empty."""
    level=str(profile.get('education_level') or '')
    if level not in EDUCATION_LEVELS:
        return 'Choose your completed education level in Applicant Profile'
    area=area_reason(job,cfg)
    if area:
        return area
    if qualification_note:
        note=qualification_note(job,cfg)
        if note:
            return note
    title=str(job.get('title') or '')
    # General management and leadership jobs aren't normal entry-level matches.
    if MANAGEMENT_RE.search(title):
        return 'Management or leadership role is not an entry-level match'
    description=str(job.get('description') or '')
    # Short excerpts are normal in some local feeds. Do not claim the applicant
    # is ineligible merely because a routine listing has a short description.
    # Display a separate "verify requirements" caution in the UI instead.
    # Explicit mandatory credentials cannot be inferred from resume keywords.
    for match in CREDENTIAL_RE.finditer(description[:11000]):
        context=description[max(0,match.start()-65):min(len(description),match.end()+70)]
        if MANDATORY_RE.search(context) and not re.search(
            r'\b(?:preferred|a plus|nice to have|optional|not required)\b',context,re.I):
            return 'Posting states a mandatory license or certification that JobPilot has not verified'
    # A fluent non-English language is an essential requirement, not a keyword overlap.
    for match in NON_ENGLISH_LANGUAGE_RE.finditer(description[:11000]):
        context=description[max(0,match.start()-65):min(len(description),match.end()+60)]
        if re.search(r'\b(?:fluen(?:t|cy)|bilingual|native speaker|proficient|must speak|'
                     r'language proficiency|translation|interpreter)\b',context,re.I) and not re.search(
                     r'\b(?:preferred|optional|nice to have|bonus|a plus)\b',context,re.I):
            return 'Posting requires specialized language fluency that JobPilot has not verified'
    required=required_education(description)
    actual=EDUCATION_LEVELS[level]
    if required>actual:
        needed=min((name for name,rank in EDUCATION_LEVELS.items() if rank==required),
                   key=lambda name:len(name),default='higher education')
        return 'Posting lists education above your confirmed '+EDUCATION_NAMES[level]+': '+EDUCATION_NAMES.get(needed,needed)
    role=role_reason(job,cfg)
    if role:
        return role
    return ''

def review_note(job):
    """Tell users when a candidate is a possible match, not verified eligibility."""
    desc=str(job.get('description') or '').strip()
    if len(desc)<100:
        return 'Limited job description. Verify education, duties and qualifications on the employer site.'
    return ''

