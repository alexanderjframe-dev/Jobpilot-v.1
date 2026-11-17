# JobPilot — personal job-search autopilot

A local-first job discovery, matching and application management app. Built to help you move toward a more stable job rather than rely on gig work alone.

## iPhone and hosted access

Use [IPHONE_SETUP.md](IPHONE_SETUP.md) for the mobile-friendly, password-protected hosting setup. The included `render.yaml` describes a **paid** Render service with a persistent disk. This repository alone is not a live website.

## Run it

**Requirements:** Python 3.10 or newer, internet access for live job feeds, a modern browser.

**Windows:** unzip this project, then double-click `run.bat`.

**macOS / Linux:** open Terminal in the unzipped project folder and run:

```bash
./run.sh
```

Then open **http://127.0.0.1:8765** on that computer. Leave the terminal open while using the app. No hosted account or database subscription is required.

If you want the automated browser form-filling feature, install Chromium *once* from the project virtual environment:

```bash
# Mac/Linux
. .venv/bin/activate
python -m playwright install chromium

# Windows Command Prompt
.venv\Scripts\activate.bat
python -m playwright install chromium
```

The app runs **only on your computer**. It won't continue scanning or applying after your computer or local server shuts down. Scheduled refreshes are opt-in, and the default interval is 12 hours.

## Resume-to-profile autofill

When you upload a PDF, DOCX, or TXT resume from Applicant Profile, JobPilot reads the text **on its server** and fills profile fields that are currently blank: name, email, phone, location, LinkedIn/portfolio links, summary, work history, education, and skills when clearly present.

- Your existing profile entries are **not overwritten**. You can review and edit every imported field.
- JobPilot never guesses work authorization or visa sponsorship answers.
- Some resume formatting and scanned/image-only PDFs cannot be read automatically; export a text-based PDF or DOCX instead.
- The parser is rule-based and may misread unusual layouts. Check the imported information before using it in a real application.
- No external AI parsing service is used; resumes stay with JobPilot's configured storage. A free Render web service may erase uploaded files and saved profiles when restarted or redeployed.

## First-time setup

1. **Applicant profile:** Add your accurate contact details, work history and skills, then upload a real resume (PDF/DOCX/TXT, 5 MB maximum).
2. **Preferences:** Adjust the **27 sliders** and text rules. Default location is Austin, TX; replace it with your actual target region. Choose role keywords, salary, scheduling and work arrangement.
3. **Job feeds:** Remotive remote jobs works without an API key. For specific employers using Greenhouse or Lever, add their public board token in Preferences. Local jobs often require employer-specific boards. You can also add job postings manually.
4. **Discover:** Click **Find jobs**. The list is weighted/rule-based (not a guarantee of eligibility). Review source listings to verify details.
5. **Queue:** Save a job, explicitly **Approve** it, then click **Apply assist**. The helper opens a visible Chromium window and tries to fill familiar form fields. It may need manual review or human-only questions.
6. **Track:** Mark an application `Applied` after you actually submit it, and use the tracker for interviews and offers. Export CSV or JSON whenever you want.

## Application automation: what works and what doesn't

- **Works now:** Public-feed search, configurable employer feeds, local persistence, score recalculation, duplicate detection, manual job addition, approval queue, browser form prefill on recognizable fields, resume attachment, activity history, export, daily launch limits, optional scheduled refresh while running.
- **Optional auto-submit:** Off by default. If explicitly enabled, it attempts a final submit **only** on a supported Greenhouse/Lever hosted application, only for an individually approved job, only if first/last name, email and resume are populated and no visible required field is missing. A job counts as `Applied` only if a confirmation message was detected. This is best-effort and not a universal system.
- **Needs your involvement:** CAPTCHAs, employer login, complex custom questionnaires, work authorization fields, consent, assessments, and reviewing information before it is shared. The assistant never bypasses these, and does not invent qualifications.
- **Not built yet:** AI-authored resume tailoring or cover letters; those two preference sliders are saved for future extension. The scoring engine is **rules-based**, not an LLM. Some sliders (e.g., approximate commute, company size and weekly hours) are retained as preferences because current feeds don't contain dependable data to enforce them.
- **Not covered:** Universal LinkedIn/Indeed/Easy Apply submission or unrestricted site scraping. Public APIs have source-specific terms and rate limits.

## Safety and privacy

- This is a **local** HTTP app bound to `127.0.0.1`, not a public server. Do not change to `0.0.0.0` or publish it on the internet.
- `data/` contains your private resume, applicant profile, logs and SQLite database. It's ignored by Git. **Never publish or share this folder.**
- Don't put fake experience, credentials, authorization answers or other invented details into your profile. Check each employer's posted requirements and terms.
- A job discovered or matched is **not** the same as a job application. `Applied` means the app detected confirmation or you explicitly recorded it yourself.
- Fictional demo jobs are marked **FICTIONAL DEMO** and can never be approved or submitted. They exist to test the UI without live requests.
- Remotive source job results are delayed and should link back to Remotive as required by its public API; the dashboard contains source attribution and each result retains its source URL. Avoid fetching Remotive too often; scans have a minimum 6-hour automated interval.

## Where data comes from

- [Remotive public job API](https://remotive.com/remote-jobs/api)
- [Greenhouse Job Board public GET API](https://docs.greenhouse.io/job-board.html)
- [Lever public postings API](https://github.com/lever/postings-api)

Greenhouse and Lever require employer board/site tokens. Note that Greenhouse's server-side applications endpoint requires authentication; this app instead uses an opt-in visible browser workflow and does not claim to own any employer API credentials.

## Files

`app.py` — FastAPI + SQLite + matching & feed adapters  
`apply_assist.py` — cautious Playwright application helper  
`static/index.html`, `static/styles.css`, `static/app.js` — web dashboard  
`data/` — created on first launch, private local data  
`tests/test_app.py` — automated backend tests

## Troubleshooting

- **No live jobs:** Check your internet connection, click Find jobs, verify your employer board tokens, and inspect Activity for source failures. Remotive only covers remote roles, so add specific employer boards for local opportunities.
- **Application browser won't open:** Run `python -m playwright install chromium` inside the app virtual environment, and make sure you're running on a desktop with a graphical session.
- **No application got sent:** Check `Needs review`. Employer forms vary widely, so open the employer's listing and finish the steps yourself. Never rely on a job status you haven't confirmed.
- **Port already in use:** Stop the other process using port 8765 or edit the port in your run script.
