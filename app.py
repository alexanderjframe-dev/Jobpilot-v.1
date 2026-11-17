"""JobPilot — local-first job discovery and application operations dashboard."""
from __future__ import annotations
import asyncio, csv, hashlib, html, io, json, os, re, sqlite3, threading, time, traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from resume_parser import extract_resume_text, parse_resume
from mobile_security import install_security, hosted_mode
from extra_job_sources import discover_more

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('JOBPILOT_DATA_DIR', str(ROOT / 'data'))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'jobpilot.sqlite3'

SLIDERS = [
 # Scoring weights
 ('weight_pay','Pay importance',65,0,100,5,'match','How much compensation influences the match score'),
 ('weight_skills','Skills fit',80,0,100,5,'match','Match job title and description with your interests and skills'),
 ('weight_location','Location / commute fit',80,0,100,5,'match','Reward jobs close to your target city or remote'),
 ('weight_remote','Remote flexibility fit',55,0,100,5,'match','Reward jobs matching your remote preference'),
 ('weight_schedule','Schedule fit',70,0,100,5,'match','Favor your preferred work schedule'),
 ('weight_seniority','Entry-level fit',85,0,100,5,'match','Penalize jobs above your requested experience level'),
 ('weight_freshness','Posting freshness',35,0,100,5,'match','Prefer recently posted jobs'),
 ('weight_keywords','Keyword preferences',75,0,100,5,'match','Reward preferred keywords and penalize excluded terms'),
 # boundaries
 ('minimum_hourly','Minimum hourly pay ($)',16,0,70,1,'requirements','Used when pay is listed; unknown pay is not automatically rejected'),
 ('target_hourly','Ideal hourly pay ($)',23,8,90,1,'requirements','Pay goal to optimize toward'),
 ('max_commute_minutes','Max commute (minutes)',35,0,120,5,'requirements','A planning preference; actual routes are not verified'),
 ('remote_preference','Remote preference (%)',35,0,100,5,'requirements','0 favors on-site, 100 favors remote'),
 ('hybrid_preference','Hybrid preference (%)',65,0,100,5,'requirements','How much you like hybrid work'),
 ('max_experience_years','Maximum required experience',2,0,10,1,'requirements','Jobs stating more may score lower'),
 ('min_weekly_hours','Minimum hours / week',30,0,60,5,'requirements','Used when hours are listed'),
 ('max_weekly_hours','Maximum hours / week',45,10,80,5,'requirements','Used when hours are listed'),
 ('max_job_age_days','Max posting age (days)',30,1,90,1,'requirements','Older listings are deprioritized'),
 ('desired_company_size','Prefer larger employers (%)',50,0,100,5,'requirements','Saved for future enrichment; company sizes are not in current feeds'),
 # automation
 ('match_threshold','Strong-match score',65,0,100,5,'automation','Score needed for a strong-match badge'),
 ('auto_queue_threshold','Auto-queue score',85,0,100,5,'automation','Eligible jobs are saved to a review queue, never submitted unapproved'),
 ('daily_application_cap','Daily application cap',12,1,100,1,'automation','Limits launches and attempted submissions per day'),
 ('refresh_hours','Refresh every (hours)',12,6,48,1,'automation','Refresh occurs while this local server is running'),
 ('max_jobs_per_feed','Jobs per source',120,10,250,10,'automation','How many jobs to load per public job feed'),
 ('resume_tailoring','Resume tailoring strength (%)',55,0,100,5,'automation','Preference saved for future AI resume drafting; not live yet'),
 ('cover_letter_length','Cover letter length (%)',35,0,100,5,'automation','Preference saved for future AI cover letter drafting; not live yet'),
 ('review_strictness','Review strictness (%)',85,0,100,5,'automation','Saved preference; submissions always require individual approval'),
 ('risk_tolerance','Uncertain-listing tolerance (%)',25,0,100,5,'automation','Saved preference; unknown fields always require review'),
]
SLIDER_MAP = {x[0]:x for x in SLIDERS}
DEFAULTS = {row[0]:row[2] for row in SLIDERS}
DEFAULTS.update({
 'location':'Austin, TX', 'location_aliases':'Liberty Hill, TX; Cedar Park, TX; Round Rock, TX',
 'target_titles':'retail associate, warehouse associate, customer service, stocker, entry level, IT support',
 'skills':'customer service, technology, AI tools, budgeting, problem solving',
 'must_have_keywords':'','avoid_keywords':'senior, principal, director, unpaid, commission only',
 'work_type':'any', 'schedule':'either', 'greenhouse_boards':'', 'lever_sites':'',
 'scan_enabled':False, 'auto_queue_enabled':False, 'auto_submit_enabled':False,
 'remote_feed_enabled':True, 'sample_mode':False,
 'jobicy_enabled':True, 'remoteok_enabled':True,
 'adzuna_enabled':True, 'jsearch_enabled':True, 'usajobs_enabled':True,
})
PROFILE_DEFAULTS = { 'first_name':'', 'last_name':'', 'email':'', 'phone':'', 'city':'', 'state':'',
 'linkedin':'','portfolio':'', 'work_authorized':'', 'sponsorship':'', 'summary':'',
 'experience':'', 'education':'', 'skills':'', 'resume_filename':'', 'resume_path':'' }

@contextmanager
def db():
 conn = sqlite3.connect(DB, timeout=30, check_same_thread=False)
 conn.row_factory = sqlite3.Row
 conn.execute('PRAGMA journal_mode=WAL')
 try:
  yield conn
  conn.commit()
 finally: conn.close()

def initialize():
 with db() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS jobs(
    id TEXT PRIMARY KEY, source TEXT, source_id TEXT, company TEXT, title TEXT,
    location TEXT, work_mode TEXT, employment_type TEXT, salary TEXT,
    min_hourly REAL, description TEXT, url TEXT, posted_at TEXT,
    sample INTEGER DEFAULT 0, status TEXT DEFAULT 'discovered', score INTEGER DEFAULT 0,
    reasons TEXT DEFAULT '[]', metrics TEXT DEFAULT '{}', created_at TEXT, updated_at TEXT,
    applied_at TEXT, notes TEXT DEFAULT ''
  );
  CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url) WHERE url IS NOT NULL AND url <> '';
  CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, message TEXT, job_id TEXT);
  CREATE TABLE IF NOT EXISTS application_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, launched_at TEXT);
  ''')
  existing=c.execute("SELECT value FROM kv WHERE key='config'").fetchone()
  if not existing:
   c.execute("INSERT INTO kv(key,value) VALUES ('config',?)",(json.dumps(DEFAULTS),))
  else:
   saved=json.loads(existing['value'])
   missing={key:value for key,value in DEFAULTS.items() if key not in saved}
   if missing:
    c.execute("UPDATE kv SET value=? WHERE key='config'",(json.dumps({**missing,**saved}),))
  if not c.execute("SELECT 1 FROM kv WHERE key='profile'").fetchone():
   c.execute("INSERT INTO kv(key,value) VALUES ('profile',?)",(json.dumps(PROFILE_DEFAULTS),))

def get_kv(key):
 with db() as c:
  r=c.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
  return json.loads(r['value']) if r else {}

def set_kv(key,value):
 with db() as c:
  c.execute('INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))

def now(): return datetime.now(timezone.utc).isoformat()
def log(message,level='info',job_id=None):
 with db() as c: c.execute('INSERT INTO activity(ts,level,message,job_id) VALUES(?,?,?,?)',(now(),level,message,job_id))

def clean_html(raw):
 return BeautifulSoup(raw or '', 'html.parser').get_text(' ', strip=True)[:13000]

def safe_url(s):
 try:
  u=urlparse(str(s));return str(s) if u.scheme in ('http','https') and u.netloc else ''
 except: return ''

def pay_rate(s):
 s = str(s or '').lower().replace(',','')
 m=re.search(r'\$\s*(\d+(?:\.\d+)?)\s*(?:-|to|–)\s*\$?\s*(\d+(?:\.\d+)?)',s)
 if m: v=float(m.group(1))
 else:
  m=re.search(r'\$\s*(\d+(?:\.\d+)?)',s)
  if not m: return None
  v=float(m.group(1))
 if 'year' in s or 'annual' in s or 'yr' in s or v>500: return round(v/2080,2)
 if 'month' in s: return round(v/173,2)
 if 'week' in s: return round(v/40,2)
 return v

def classify_mode(title,location,description='',remote_override=None):
 if remote_override is True: return 'remote'
 txt=(title+' '+location+' '+description[:300]).lower()
 if 'hybrid' in txt: return 'hybrid'
 if re.search(r'\bremote\b|work from home|work-from-home',txt): return 'remote'
 return 'onsite'

def token_set(s):
 return {x for x in re.findall(r'[a-z0-9+#.]+', (s or '').lower()) if len(x)>2 and x not in {'and','the','with','from','that','this','for','you','our','are','will','your','job','work','more','have'}}

# Senior-level titles and clearly stated experience requirements should not
# qualify as normal entry-level recommendations just because pay/skills align.
ADVANCED_TITLE_RE = re.compile(
 r'\b(?:senior|sr\.?|principal|staff|distinguished|director|vice president|'
 r'vp|chief|head of|cto|tech(?:nical)? lead|engineering lead|'
 r'lead (?:software|full[\s-]?stack|back[\s-]?end|front[\s-]?end|rails|'
 r'python|java|data|machine|security|devops|platform|cloud|engineer|'
 r'architect|technical|tech|product|developer)|'
 r'(?:software|data|engineering|platform|security|product) lead|'
 r'(?:general|regional|district|engineering) manager)\b',re.I)
EXP_YEARS_RE = re.compile(r'\b(\d{1,2})\s*(?:\+|plus\b|[-–]\s*\d{1,2})?\s*(?:years?|yrs?)\b',re.I)
ENTERPRISE_ROLE_RE = re.compile(r'\b(?:sales engineer|solutions? engineer|account executive|sales executive|customer success manager|technical account manager|solutions? architect|sales manager|account manager)\b',re.I)
# Roles with essential language proficiency or professional licenses should not
# appear as ordinary matches without a way to verify those qualifications.
LANGUAGE_ROLE_RE = re.compile(r'\\b(?:interpreters?|translators?|linguists?)\\b',re.I)
MULTILINGUAL_ROLE_RE = re.compile(r'\\b(?:bilingual|multilingual|tri\\s?lingual)\\b',re.I)
LICENSED_ROLE_RE = re.compile(r'\\b(?:registered nurse|licensed practical nurse|physician|attorney|lawyer|dentist|pharmacist|commercial pilot|airline pilot|certified public accountant|cdl(?:[ -]?[ab])?|licensed\\s+\\w+(?:\\s+\\w+)?)\\b',re.I)

def qualification_note(job,cfg):
 """Conservative title/required-years warning; not a verified eligibility ruling."""
 title=str(job.get('title') or '')
 if ADVANCED_TITLE_RE.search(title):
  return 'Senior or leadership-level title; outside entry-level recommendations'
 if re.search(r'\benterprise\b',title,re.I) and ENTERPRISE_ROLE_RE.search(title):
  return 'Enterprise-level sales or client leadership role; outside entry-level recommendations'
 if LANGUAGE_ROLE_RE.search(title):
  return 'Interpreter/translator role requires proficiency in the stated language(s); JobPilot has not verified your fluency'
 if MULTILINGUAL_ROLE_RE.search(title):
  return 'Bilingual or multilingual role requires language proficiency that JobPilot has not verified'
 if LICENSED_ROLE_RE.search(title):
  return 'Role likely requires a specific professional license or certification; verify requirements before applying'
 desc=str(job.get('description') or '')[:10000]
 limit=max(0,int(cfg.get('max_experience_years',2)))
 for match in EXP_YEARS_RE.finditer(desc):
  years=int(match.group(1))
  if years<=limit or years>35:
   continue
  context=desc[max(0,match.start()-85):min(len(desc),match.end()+90)].lower()
  # Avoid tagging tenure, company age or bonus qualifications.
  if not re.search(r'\b(experience|required|minimum|at least|must have|'
                   r'qualifications|hands.on|professional|work history)\b',context):
   continue
  if re.search(r'\b(preferred|nice to have|bonus|desirable|optional)\b',context) and not re.search(r'\b(required|must have|minimum|at least)\b',context):
   continue
  return f'Listing mentions {years} years of experience; your selected limit is {limit}'
 return ''

def score_job(job, cfg, profile):
 title=(job.get('title') or '').lower(); txt=title+' '+(job.get('description') or '').lower()
 preferred=[x.strip().lower() for x in (cfg.get('target_titles','')+';'+cfg.get('skills','')+';'+profile.get('skills','')).replace(',', ';').split(';') if x.strip()]
 fav=token_set(' '.join(preferred))
 target=token_set(title+' '+(job.get('description') or '')[:1000])
 intersect=fav & target
 title_overlap=len(fav & token_set(title))
 skills=min(100, round(40 + (len(intersect)/max(1,len(fav)))*115 + min(title_overlap*11,33))) if fav else 55
 if any(t in title for t in ('senior','principal','staff engineer','director','head of','vp ','vice president','manager ii')): senior=12
 elif any(t in title for t in ('entry','junior','associate','assistant','trainee','apprentice','intern')): senior=100
 else: senior=73
 years=re.search(r'(\d+)\+?\s*(?:years|yrs)\s*(?:of)?\s*(?:experience)?',txt[:3000])
 if years:
  v=int(years.group(1)); senior=max(0,senior - max(0,v-int(cfg['max_experience_years']))*20)
 rate=job.get('min_hourly')
 if rate is not None:
  goal=max(1,float(cfg['target_hourly']));pay=round(min(100,rate/goal*100))
  if rate<float(cfg['minimum_hourly']): pay=max(0,pay-40)
 else: pay=52
 mode=job.get('work_mode','onsite')
 remote_pref=cfg['remote_preference']/100
 remote={'remote':round(remote_pref*100),'hybrid':round(cfg['hybrid_preference']),'onsite':round((1-remote_pref)*100)}.get(mode,50)
 if mode=='remote': loc=100
 else:
  hay=(job.get('location') or '').lower()
  loc_city=cfg['location'].split(',')[0].strip().lower()
  alt=[x.strip().split(',')[0].lower() for x in cfg.get('location_aliases','').split(';') if x.strip()]
  loc=100 if any(t and t in hay for t in [loc_city]+alt) else 34
  if 'united states'==hay.strip() or hay=='usa':loc=58
 schedule=cfg['schedule']
 emp=(job.get('employment_type') or '').lower()
 if schedule=='either' or not emp: sched=75
 elif schedule=='full' and ('full' in emp or 'permanent' in emp):sched=100
 elif schedule=='part' and 'part' in emp:sched=100
 else:sched=28
 freshness=55
 try:
  if job.get('posted_at'):
   ts=datetime.fromisoformat(job['posted_at'].replace('Z','+00:00'))
   age=max(0,(datetime.now(timezone.utc)-ts.astimezone(timezone.utc)).days)
   freshness=max(0,round(100*(1-age/max(1,cfg['max_job_age_days']))))
 except:pass
 must=[x.strip().lower() for x in cfg.get('must_have_keywords','').split(',') if x.strip()]
 avoid=[x.strip().lower() for x in cfg.get('avoid_keywords','').split(',') if x.strip()]
 keyword=75 if not must else 100 if all(k in txt for k in must) else 10
 keyword=max(0,keyword-35*sum(k in txt for k in avoid))
 metrics={'pay':pay,'skills':skills,'location':loc,'remote':remote,'schedule':sched,'seniority':senior,'freshness':freshness,'keywords':keyword}
 weights={'pay':cfg['weight_pay'],'skills':cfg['weight_skills'],'location':cfg['weight_location'], 'remote':cfg['weight_remote'], 'schedule':cfg['weight_schedule'], 'seniority':cfg['weight_seniority'], 'freshness':cfg['weight_freshness'], 'keywords':cfg['weight_keywords']}
 denominator=sum(weights.values()) or 1
 score=round(sum(weights[k]*metrics[k] for k in weights)/denominator)
 if cfg.get('work_type')=='remote' and mode!='remote':score=max(0,score-28)
 if cfg.get('work_type')=='onsite' and mode=='remote':score=max(0,score-15)
 level_warning=qualification_note(job,cfg)
 if level_warning:score=min(score,30)
 reasons=[]
 if level_warning:reasons.append(level_warning)
 if title_overlap: reasons.append('Title aligns with your interests')
 if mode=='remote':reasons.append('Remote-friendly')
 elif loc>=90: reasons.append('Near your target area')
 if rate and rate>=cfg['minimum_hourly']:reasons.append('Meets your pay floor')
 if senior>=90:reasons.append('Entry-level friendly')
 if keyword<40:reasons.append('Contains excluded terms')
 if rate is None:reasons.append('Pay not disclosed')
 return max(0,min(100,score)),reasons[:4],metrics

def upsert_jobs(items):
 cfg=get_kv('config'); profile=get_kv('profile'); new_count=0; total=0
 with db() as c:
  for j in items:
   url=safe_url(j.get('url',''))
   if not url: continue
   source=str(j.get('source','Manual'))[:60]
   ident=j.get('source_id') or url
   jid=hashlib.sha256((source+'|'+str(ident)).encode()).hexdigest()[:24]
   j=dict(j);j['url']=url
   j['min_hourly']=j.get('min_hourly') if j.get('min_hourly') is not None else pay_rate(j.get('salary'))
   score,reasons,metrics=score_job(j,cfg,profile)
   old=c.execute('SELECT id,status FROM jobs WHERE id=? OR url=?',(jid,url)).fetchone()
   if old:
    c.execute('''UPDATE jobs SET score=?,reasons=?,metrics=?,updated_at=?, description=?,salary=?,min_hourly=? WHERE id=?''',
              (score,json.dumps(reasons),json.dumps(metrics),now(),j.get('description','')[:13000],j.get('salary',''),j.get('min_hourly'),old['id']))
   else:
    status='saved' if cfg.get('auto_queue_enabled') and score>=cfg['auto_queue_threshold'] and not j.get('sample') else 'discovered'
    c.execute('''INSERT INTO jobs(id,source,source_id,company,title,location,work_mode,employment_type,salary,min_hourly,description,url,posted_at,sample,status,score,reasons,metrics,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (jid,source,str(ident),str(j.get('company') or 'Unknown')[:200],str(j.get('title') or 'Untitled')[:200],str(j.get('location') or '')[:200],str(j.get('work_mode') or 'onsite'),str(j.get('employment_type') or '')[:80],str(j.get('salary') or '')[:120],j['min_hourly'],str(j.get('description') or '')[:13000],url,j.get('posted_at'),int(bool(j.get('sample'))),status,score,json.dumps(reasons),json.dumps(metrics),now(),now()))
    new_count+=1
   total+=1
 return {'new':new_count,'processed':total}

def normalized_date(v):
 if not v:return None
 try:
  if isinstance(v,(float,int)):return datetime.fromtimestamp(v,timezone.utc).isoformat()
  return datetime.fromisoformat(str(v).replace('Z','+00:00')).isoformat()
 except:return None

async def fetch_jobs():
 cfg=get_kv('config'); items=[];errors=[]; counts={}
 async with httpx.AsyncClient(timeout=18,headers={'User-Agent':'JobPilot/1.0 (local personal job discovery tool)','Accept':'application/json'},follow_redirects=True) as client:
  async def grab(name,url,parser):
   try:
    r=await client.get(url);r.raise_for_status();arr=parser(r.json());
    if not isinstance(arr,list):raise ValueError('feed did not return a list')
    items.extend(arr[:cfg['max_jobs_per_feed']]); counts[name]=len(arr[:cfg['max_jobs_per_feed']])
   except Exception as e:
    errors.append(f'{name}: {str(e)[:120]}');counts[name]=0
  if cfg.get('remote_feed_enabled',True):
   def remotive(js):
    return [{'source':'Remotive','source_id':x.get('id'),'title':x.get('title'),'company':x.get('company_name'),'location':x.get('candidate_required_location') or 'Remote','work_mode':'remote','employment_type':x.get('job_type') or '', 'description':clean_html(x.get('description')),'url':x.get('url'),'salary':x.get('salary') or '','posted_at':normalized_date(x.get('publication_date'))} for x in js.get('jobs',[])]
   await grab('Remotive','https://remotive.com/api/remote-jobs?limit='+str(cfg['max_jobs_per_feed']),remotive)
  def sites(value): return list(dict.fromkeys([x.strip().lower() for x in re.split('[,;\n]',value or '') if re.fullmatch('[a-zA-Z0-9_-]{2,60}',x.strip())]))[:12]
  for token in sites(cfg.get('greenhouse_boards')):
   def gh(js,token=token):
    out=[]
    for x in js.get('jobs',[]):
     loc=(x.get('location') or {}).get('name','')
     title=x.get('title','')
     desc=clean_html(x.get('content'))
     out.append({'source':'Greenhouse / '+token,'source_id':x.get('id'),'title':title,'company':token.replace('-',' ').title(),'location':loc,'work_mode':classify_mode(title,loc,desc),'employment_type':'','description':desc,'url':x.get('absolute_url'),'salary':'','posted_at':normalized_date(x.get('updated_at'))})
    return out
   await grab('Greenhouse: '+token,'https://boards-api.greenhouse.io/v1/boards/'+token+'/jobs?content=true',gh)
  for token in sites(cfg.get('lever_sites')):
   def lev(js,token=token):
    out=[]
    for x in js:
     cats=x.get('categories') or {}; loc=cats.get('location') or ''
     title=x.get('text') or ''
     desc=clean_html(x.get('descriptionPlain') or x.get('description') or '')
     out.append({'source':'Lever / '+token,'source_id':x.get('id'),'title':title,'company':token.replace('-',' ').title(),'location':loc,'work_mode':classify_mode(title,loc,desc),'employment_type':cats.get('commitment') or '', 'description':desc,'url':x.get('hostedUrl') or x.get('applyUrl'),'salary':'','posted_at':normalized_date((x.get('createdAt') or 0)/1000)})
    return out
   await grab('Lever: '+token,'https://api.lever.co/v0/postings/'+token+'?mode=json',lev)
  await discover_more(client, cfg, items, counts, errors)
 if not items and not errors:errors.append('No sources enabled. Enable Remotive or add an employer board token.')
 result=upsert_jobs(items)
 set_kv('last_scan',{'at':now(),'counts':counts,'errors':errors,**result})
 log(f"Feed refresh: {result['new']} new jobs, {result['processed']} checked" + (f"; {len(errors)} source errors" if errors else ''), 'warning' if errors else 'success')
 return get_kv('last_scan')

def jobs_dict(rows):
 out=[];cfg=get_kv('config')
 for r in rows:
  d=dict(r)
  for key in ('reasons','metrics'):
   try:d[key]=json.loads(d[key])
   except:d[key]=[] if key=='reasons' else {}
  warning=qualification_note(d,cfg)
  d['advanced']=bool(warning)
  d['qualification_note']=warning
  d['sample']=bool(d['sample']);out.append(d)
 return out

def recalculate():
 cfg=get_kv('config');profile=get_kv('profile')
 with db() as c:
  for job in c.execute('SELECT * FROM jobs').fetchall():
   score,reasons,metrics=score_job(dict(job),cfg,profile)
   c.execute('UPDATE jobs SET score=?,reasons=?,metrics=? WHERE id=?',(score,json.dumps(reasons),json.dumps(metrics),job['id']))

app=FastAPI(title='JobPilot',version='1.1.0')
install_security(app)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
initialize()
recalculate()  # Apply new qualification limits to listings from prior scans.
scan_lock=asyncio.Lock()

class JsonObject(BaseModel):
 values:dict[str,Any]=Field(default_factory=dict)
class ManualJob(BaseModel):
 title:str=Field(min_length=2,max_length=200)
 company:str=Field(min_length=2,max_length=200)
 url:str=Field(min_length=8,max_length=2000)
 location:str=''
 salary:str=''
 description:str=''
 employment_type:str=''
 work_mode:str='onsite'
class StatusChange(BaseModel):
 status:str
 notes:str|None=None

@app.get('/healthz')
async def healthz():return {'status':'ok'}

@app.get('/',response_class=HTMLResponse)
async def index():return (ROOT/'static'/'index.html').read_text(encoding='utf-8')
@app.get('/api/bootstrap')
async def bootstrap():
 with db() as c:
  counts={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) AS n FROM jobs GROUP BY status')}
  stats={'total':sum(counts.values()),'strong':c.execute('SELECT COUNT(*) AS n FROM jobs WHERE score>=? AND sample=0',(get_kv('config')['match_threshold'],)).fetchone()['n'], 'approved':counts.get('approved',0),'applied':counts.get('applied',0),'sample':c.execute('SELECT COUNT(*) n FROM jobs WHERE sample=1').fetchone()['n']}
 return {'hosted':hosted_mode(),'provider_keys':{'adzuna':bool(os.environ.get('ADZUNA_APP_ID') and os.environ.get('ADZUNA_APP_KEY')),'jsearch':bool(os.environ.get('JSEARCH_API_KEY')),'usajobs':bool(os.environ.get('USAJOBS_API_KEY') and os.environ.get('USAJOBS_EMAIL'))},'config':get_kv('config'),'profile':get_kv('profile'),'sliders':[dict(zip(['key','name','default','min','max','step','group','help'],s)) for s in SLIDERS],'stats':stats,'last_scan':get_kv('last_scan')}

@app.put('/api/config')
async def save_config(payload:JsonObject):
 old=get_kv('config'); updated=dict(old)
 for k,v in payload.values.items():
  if k in SLIDER_MAP:
   spec=SLIDER_MAP[k]
   try:v=int(float(v))
   except:continue
   updated[k]=max(spec[3],min(spec[4],v))
  elif k in old:
   if isinstance(old[k],bool): updated[k]=bool(v) if isinstance(v,bool) else str(v).lower()=='true'
   elif isinstance(old[k],str):updated[k]=str(v)[:1600]
 # no automatic submits in recurring scans; mode only allows manually approved per-job run
 set_kv('config',updated);recalculate();log('Preferences updated')
 return {'ok':True,'config':updated}

@app.put('/api/profile')
async def save_profile(payload:JsonObject):
 old=get_kv('profile')
 for k,v in payload.values.items():
  if k in old and k not in ('resume_path','resume_filename'):
   old[k]=str(v)[:5000]
 set_kv('profile',old);recalculate();log('Applicant profile updated')
 return {'ok':True,'profile':old}

@app.post('/api/resume')
async def upload_resume(file:UploadFile=File(...)):
 suffix=Path(file.filename or '').suffix.lower()
 if suffix not in ('.pdf','.docx','.txt'):
  raise HTTPException(400,'Resume must be PDF, DOCX, or TXT')
 raw=await file.read(5_000_001)
 if len(raw)>5_000_000:raise HTTPException(400,'Resume must be 5MB or less')
 if suffix=='.pdf' and not raw.startswith(b'%PDF'):raise HTTPException(400,'Invalid PDF')
 if suffix=='.docx' and not raw.startswith(b'PK'):raise HTTPException(400,'Invalid DOCX')
 path=DATA/('resume'+suffix);path.write_bytes(raw)
 text,warning=extract_resume_text(raw,suffix)
 extracted=parse_resume(text)
 p=get_kv('profile')
 filled=[]
 for key,value in extracted.items():
  if key in PROFILE_DEFAULTS and key not in ('resume_path','resume_filename','work_authorized','sponsorship') and not str(p.get(key,'')).strip():
   p[key]=value[:5000]
   filled.append(key)
 p['resume_filename']=Path(file.filename or 'resume').name[:120]
 p['resume_path']=str(path)
 set_kv('profile',p)
 if filled:recalculate()
 log('Resume uploaded; ' + str(len(filled)) + ' blank profile fields auto-filled')
 return {'ok':True,'filename':p['resume_filename'],'autofill':{'filled':filled,'found':list(extracted.keys()),'warning':warning or ('No recognizable applicant details found in this resume.' if not extracted else '')}}

@app.get('/api/jobs')
async def list_jobs(query:str='',status:str='',min_score:int=0,sort:str='score',include_samples:bool=True,include_advanced:bool=False,limit:int=500):
 with db() as c:
  rows=jobs_dict(c.execute('SELECT * FROM jobs ORDER BY score DESC,created_at DESC LIMIT 2500').fetchall())
 q=query.strip().lower()
 if q:rows=[j for j in rows if q in (j['title']+' '+j['company']+' '+j['location']+' '+j['description'][:1500]).lower()]
 if status:rows=[j for j in rows if j['status']==status]
 hidden_advanced=sum(1 for j in rows if j['advanced'] and j['status'] in ('discovered','skipped'))
 if not include_advanced:rows=[j for j in rows if not j['advanced'] or j['status'] not in ('discovered','skipped')]
 cfg=get_kv('config')
 if cfg.get('work_type')=='remote':rows=[j for j in rows if j['work_mode']=='remote']
 must=[x.strip().lower() for x in cfg.get('must_have_keywords','').split(',') if x.strip()]
 if must:rows=[j for j in rows if all(k in (j['title']+' '+j['description']).lower() for k in must)]
 if min_score: rows=[j for j in rows if j['score']>=min_score]
 if not include_samples:rows=[j for j in rows if not j['sample']]
 if sort=='recent':rows.sort(key=lambda x:x['posted_at'] or '',reverse=True)
 elif sort=='company':rows.sort(key=lambda x:x['company'].lower())
 elif sort=='pay':rows.sort(key=lambda x:x['min_hourly'] or 0,reverse=True)
 else:rows.sort(key=lambda x:x['score'],reverse=True)
 return {'jobs':rows[:max(1,min(limit,1000))],'total':len(rows),'hidden_advanced':hidden_advanced if not include_advanced else 0}

@app.post('/api/refresh')
async def refresh():
 if scan_lock.locked():raise HTTPException(409,'A refresh is already in progress')
 async with scan_lock:return await fetch_jobs()

@app.post('/api/jobs/manual')
async def manual_job(payload:ManualJob):
 j=payload.model_dump(); j['source']='Manual';j['source_id']=j['url'];j['description']=clean_html(j['description'])
 if not safe_url(j['url']):raise HTTPException(400,'A valid https:// or http:// job URL is required')
 upsert_jobs([j]);log('Manual job added: '+j['title']);return {'ok':True}

@app.post('/api/jobs/demo')
async def sample_jobs():
 demo=[
  ('Retail Associate','Example Market','Austin, TX','onsite','full-time','$18–$21/hour','Entry-level customer service, stocking merchandise, and assisting shoppers. Paid training.','2026-11-12'),
  ('Warehouse Fulfillment Associate','Sample Logistics','Round Rock, TX','onsite','full-time','$20/hour','Packing, inventory, shipping and warehouse operations. Entry level training.','2026-11-11'),
  ('Remote Customer Support Agent','Demo Support Co','United States - Remote','remote','full-time','$19/hour','Customer support by chat, email and phone. Entry level.','2026-11-13'),
  ('Junior IT Help Desk','Example Tech Group','Austin, TX','hybrid','full-time','$23/hour','Junior entry level IT support. Troubleshooting, tickets, password resets.','2026-11-10'),
  ('Seasonal Store Associate','Example Outfitters','Cedar Park, TX','onsite','part-time','$17/hour','Seasonal part time retail support, stocking and register.','2026-11-14'),
  ('Senior Sales Director','Sample Global Corp','Remote','remote','full-time','$140,000/year','8 years of experience. Senior director sales strategy.','2026-11-09')]
 items=[]
 for i,(title,company,loc,mode,emp,salary,desc,date) in enumerate(demo):
  items.append({'source':'DEMO — fictional','source_id':'demo-'+str(i),'title':title,'company':company,'location':loc,'work_mode':mode,'employment_type':emp,'salary':salary,'description':desc,'url':'https://example.com/jobpilot-demo-'+str(i),'posted_at':date+'T12:00:00+00:00','sample':True})
 r=upsert_jobs(items);log('Loaded fictional sample listings');return r

@app.delete('/api/jobs/demo')
async def delete_samples():
 with db() as c:c.execute('DELETE FROM jobs WHERE sample=1')
 log('Removed sample listings');return {'ok':True}

@app.patch('/api/jobs/{job_id}')
async def update_job(job_id:str,payload:StatusChange):
 allowed={'discovered','saved','approved','preparing','needs_review','applied','interview','offer','rejected','skipped'}
 if payload.status not in allowed:raise HTTPException(400,'Invalid status')
 with db() as c:
  r=c.execute('SELECT title,sample FROM jobs WHERE id=?',(job_id,)).fetchone()
  if not r:raise HTTPException(404,'Job not found')
  if r['sample'] and payload.status in ('approved','preparing','applied'):raise HTTPException(400,'Sample jobs cannot be submitted')
  if payload.notes is None:
   c.execute('UPDATE jobs SET status=?,updated_at=?,applied_at=CASE WHEN ?="applied" THEN ? ELSE applied_at END WHERE id=?',(payload.status,now(),payload.status,now(),job_id))
  else:
   c.execute('UPDATE jobs SET status=?,notes=?,updated_at=?,applied_at=CASE WHEN ?="applied" THEN ? ELSE applied_at END WHERE id=?',(payload.status,payload.notes[:4000],now(),payload.status,now(),job_id))
 log(f'{r["title"]}: {payload.status}',job_id=job_id)
 return {'ok':True}

@app.post('/api/jobs/{job_id}/apply')
async def apply_job(job_id:str):
 with db() as c:
  r=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
  if not r:raise HTTPException(404,'Job not found')
  if r['sample']:raise HTTPException(400,'Cannot apply to demo listings')
  if r['status']!='approved':raise HTTPException(400,'Approve this specific job first')
  if hosted_mode():
   return {'ok':True,'manual':True,'url':safe_url(r['url']),
           'message':'Open the employer application in Safari. No application has been submitted.'}
  p=get_kv('profile'); required=['first_name','last_name','email']
  missing=[k for k in required if not p.get(k)]
  if missing:raise HTTPException(400,'Complete your applicant profile first: '+', '.join(missing))
  today=datetime.now(timezone.utc).date().isoformat()
  attempted=c.execute('SELECT COUNT(*) n FROM application_attempts WHERE launched_at LIKE ?',(today+'%',)).fetchone()['n']
  if attempted>=get_kv('config')['daily_application_cap']:raise HTTPException(429,'Daily application cap reached')
  c.execute('UPDATE jobs SET status="preparing",updated_at=? WHERE id=?',(now(),job_id))
  c.execute('INSERT INTO application_attempts(job_id,launched_at) VALUES(?,?)',(job_id,now()))
 # spawn independently; creates visible Chromium instance on user's local computer
 import subprocess,sys
 try:
  subprocess.Popen([sys.executable,str(ROOT/'apply_assist.py'),job_id],cwd=str(ROOT),stdout=open(DATA/'assistant.log','a'),stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'JOBPILOT_DATA_DIR':str(DATA)})
 except Exception as e:
  with db() as c:c.execute('UPDATE jobs SET status="needs_review",notes=? WHERE id=?',('Unable to launch browser: '+str(e),job_id))
  raise HTTPException(500,'Browser automation failed to launch: '+str(e))
 log('Browser application assistant launched',job_id=job_id)
 return {'ok':True,'message':'An application browser is opening on your computer. Check it for review or submission.'}

@app.get('/api/activity')
async def activity():
 with db() as c:return {'events':[dict(x) for x in c.execute('SELECT * FROM activity ORDER BY id DESC LIMIT 120').fetchall()]}

@app.get('/api/export.csv')
async def export_csv():
 with db() as c:rows=jobs_dict(c.execute('SELECT * FROM jobs ORDER BY score DESC').fetchall())
 out=io.StringIO(); fields=['company','title','location','work_mode','salary','source','score','status','url','posted_at','applied_at','notes']
 writer=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
 return Response(content=out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="jobpilot-applications.csv"'})

@app.get('/api/export.json')
async def export_json():
 with db() as c: rows=jobs_dict(c.execute('SELECT * FROM jobs').fetchall())
 data={'exported_at':now(),'jobs':rows,'config':get_kv('config')}
 return Response(content=json.dumps(data,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="jobpilot-backup.json"'})

@app.on_event('startup')
async def startup():
 async def scheduler():
  while True:
   try:
    cfg=get_kv('config')
    if cfg.get('scan_enabled') and not scan_lock.locked():
     last=get_kv('last_scan').get('at')
     age=(datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds()/3600 if last else 9999
     if age>=cfg.get('refresh_hours',12):
      async with scan_lock:await fetch_jobs()
   except Exception as exc:log('Scheduled scan issue: '+str(exc)[:140],'warning')
   await asyncio.sleep(120)
 app.state.scheduler=asyncio.create_task(scheduler())

@app.on_event('shutdown')
async def shutdown():
 if getattr(app.state,'scheduler',None):app.state.scheduler.cancel()
