"""Conservative application helper for approved jobs.

This assistant uses an ordinary visible browser. It never bypasses CAPTCHAs,
misrepresents qualifications, or silently treats an unconfirmed submission as sent.
Automated submit is opt-in globally AND requires per-job approval.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from app import db, get_kv, log, now


def set_status(jid,status,message):
 with db() as c:
  c.execute('UPDATE jobs SET status=?,notes=?,updated_at=?,applied_at=CASE WHEN ?="applied" THEN ? ELSE applied_at END WHERE id=?',
            (status,message[:4000],now(),status,now(),jid))
 log(message,'success' if status=='applied' else 'info',jid)


def fill_selector(page,selectors,value):
 if not value:return False
 for selector in selectors:
  try:
   loc=page.locator(selector).first
   if loc.count() and loc.is_visible():loc.fill(str(value),timeout=1500);return True
  except:pass
 return False


def required_missing(page):
 missing=[]
 try:
  els=page.locator('input[required],select[required],textarea[required]')
  for i in range(min(els.count(),45)):
   el=els.nth(i)
   if not el.is_visible():continue
   typ=(el.get_attribute('type') or '').lower()
   if typ in ('hidden','submit','button','file'):continue
   if typ in ('checkbox','radio'):
    if not el.is_checked():missing.append(el.get_attribute('name') or 'checkbox')
   elif not el.input_value(): missing.append(el.get_attribute('name') or el.get_attribute('id') or 'required field')
 except Exception:pass
 return missing


def main(jid):
 with db() as c:
  row=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
 if not row: return
 profile=get_kv('profile');cfg=get_kv('config')
 auto=bool(cfg.get('auto_submit_enabled'))
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=False)
   context=browser.new_context(accept_downloads=True,viewport={'width':1280,'height':900})
   page=context.new_page()
   page.goto(row['url'],wait_until='domcontentloaded',timeout=40000)
   page.wait_for_timeout(1800)
   # Some employer-hosted listings hide the form behind a non-submitting "Apply for this job" CTA.
   if 'greenhouse' in (row['source'] or '').lower() or 'lever' in (row['source'] or '').lower():
    for selector in ['a:has-text("Apply for this job")','a:has-text("Apply now")']:
     try:
      cta=page.locator(selector).first
      if cta.count() and cta.is_visible():
       cta.click(timeout=2000);page.wait_for_timeout(750);break
     except:pass
   filled={}
   filled['first_name']=fill_selector(page,['input[name="first_name"]','input[name="candidate[first_name]"]','input[id*="first_name"]','input[autocomplete="given-name"]'],profile.get('first_name'))
   filled['last_name']=fill_selector(page,['input[name="last_name"]','input[name="candidate[last_name]"]','input[id*="last_name"]','input[autocomplete="family-name"]'],profile.get('last_name'))
   filled['email']=fill_selector(page,['input[type="email"]','input[name="email"]','input[autocomplete="email"]'],profile.get('email'))
   filled['phone']=fill_selector(page,['input[type="tel"]','input[name="phone"]','input[autocomplete="tel"]'],profile.get('phone'))
   filled['linkedin']=fill_selector(page,['input[name*="linkedin" i]','input[id*="linkedin" i]'],profile.get('linkedin'))
   filled['portfolio']=fill_selector(page,['input[name*="portfolio" i]','input[id*="website" i]'],profile.get('portfolio'))
   uploaded=False
   resume=profile.get('resume_path')
   if resume and Path(resume).is_file():
    try:
     uploads=page.locator('input[type="file"]')
     if uploads.count():uploads.first.set_input_files(resume,timeout=4500);uploaded=True
    except Exception:pass
   missing=required_missing(page)
   log(f'Autofill opened {row["title"]}: {sum(filled.values())} fields; resume {"attached" if uploaded else "not attached"}; {len(missing)} required fields unfilled',job_id=jid)
   is_supported=('greenhouse' in (row['source'] or '').lower() or 'lever' in (row['source'] or '').lower())
   can_auto=auto and is_supported and all(filled.get(x) for x in ('first_name','last_name','email')) and uploaded and not missing
   if can_auto:
    try:
     buttons=page.locator('button:has-text("Submit Application"),input[type="submit"][value*="Submit" i],button:has-text("Submit application")')
     if buttons.count()==1 and buttons.first.is_visible() and not page.locator('iframe[src*="captcha"],iframe[src*="recaptcha"],.g-recaptcha,.h-captcha').count():
      buttons.first.click(timeout=6000)
      page.wait_for_timeout(3500)
      body=page.locator('body').inner_text(timeout=4000).lower()[:2500]
      if any(s in body for s in ('thank you for applying','application has been submitted','application submitted','we received your application','thank you for your application')):
       set_status(jid,'applied','Submission confirmation detected on employer site.')
       browser.close();return
    except Exception as e:log('Automatic send was not confirmed: '+str(e)[:160],'warning',jid)
   why=('Required or custom fields need your review: '+', '.join(missing[:6])) if missing else ('Review pre-filled fields and submit in the browser, then mark Applied in JobPilot.' if not auto else 'Automatic submission was unavailable or could not be confirmed; review the employer form.')
   set_status(jid,'needs_review',why)
   print('Browser opened for review. Close the browser window when done.')
   deadline=time.time()+600
   while time.time()<deadline:
    try:
     if page.is_closed():break
     page.wait_for_timeout(1750)
    except:break
   browser.close()
 except Exception as e:
  set_status(jid,'needs_review',f'Browser assistant could not complete: {e}. Try installing Chromium using: python -m playwright install chromium')
  print('Browser assistant error:',str(e),file=sys.stderr)

if __name__=='__main__':
 if len(sys.argv)<2:raise SystemExit('Usage: python apply_assist.py JOB_ID')
 main(sys.argv[1])
