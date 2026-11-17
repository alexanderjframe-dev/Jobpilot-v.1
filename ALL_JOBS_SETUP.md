# JobPilot — Broad job search setup

JobPilot cannot truthfully retrieve every job on the internet. Employers use private and public systems, and many postings expire. It now combines documented public APIs, optional broader aggregation APIs, and direct search buttons for major job boards.

## Immediate sources — no account or key required

- Remotive: remote positions.
- Jobicy: remote jobs that include positions available to US applicants. Original source link is preserved.
- Remote OK: remote roles. Check whether employers accept applicants in your country.
- Greenhouse and Lever: public employer boards; add specific employer board tokens under Preferences to enable these.

Job cards credit the source. Imported postings are not individually confirmed open. Avoid refreshing repeatedly: public APIs have usage limits. Jobicy asks integrations to run automated scans no more frequently than once per hour.

## More local jobs — opt-in API providers

Go to Applicant Preferences and correct your **Primary search city**. The starter city is Austin, TX, which may not be your location. Save your changes before scanning.

**Adzuna:** Get an App ID and App Key from https://developer.adzuna.com/ and add them as environment variables ADZUNA_APP_ID and ADZUNA_APP_KEY in Render. Adzuna covers varied local jobs; the integration performs an all-jobs search and several role-specific searches in your configured city. A free developer key is available, subject to Adzuna's terms.

**JSearch:** Obtain a key and review the credit limits/pricing at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch . Add JSEARCH_API_KEY in Render. This third-party aggregator may return jobs published on Indeed, LinkedIn and other sites. The app limits itself to three queries per scan to control API credits. JSearch is NOT an official unrestricted Indeed API.

**USAJOBS:** Register for an API key at https://developer.usajobs.gov/ and add USAJOBS_API_KEY plus USAJOBS_EMAIL (your registered email) to Render. The integration searches federal jobs around your selected location.

Under Render → your Web Service → Environment, create those variables, save and allow redeployment. Do not paste API keys into GitHub, your JobPilot profile, or this chat. Provider checkboxes in JobPilot do NOT automatically obtain keys.

## Indeed, Google Jobs and LinkedIn — no API key needed

On Discover Jobs, enter an optional search keyword and tap Indeed, Google Jobs, or LinkedIn. Leave the keyword empty for a broad city-level search. Each button opens the corresponding website directly; it does NOT import those results into JobPilot. After verifying an interesting vacancy, you can use Add job manually to track it.

JobPilot does not log into or scrape Indeed. Indeed's documented partner APIs are predominantly for publishers, employers, applications and ATS posting workflows, not unrestricted retrieval of search results.

## Troubleshooting low job counts

1. Set Primary search city to your actual target city; add nearby cities where useful.
2. Set work type to Any unless you only want remote jobs.
3. Enable Jobicy, Remote OK, and Remotive; save your Preferences.
4. Remove strict Must-have keywords that could hide listings.
5. On Discover Jobs, set Min score to zero and Status to All.
6. Tap Find jobs, then read the per-source counts and API errors. Credentials are required for Adzuna, JSearch, and USAJOBS local data.
7. Review actual job pages to confirm current openings, locations and qualifications.

JobPilot fetches a bounded number of jobs per source rather than paging indefinitely. Two sources may return the same employer opening; some older saved posts may remain even if the source no longer lists them. Zero errors do NOT guarantee all active openings have been indexed.

## Privacy and free hosting

Keep the JobPilot password enabled. Free Render services without a persistent disk can lose profile information, resume files, and applications during restarts or redeploys. Back up important information.

## Sources

- https://jobicy.com/jobs-rss-feed
- https://remoteok.com/faq
- https://developer.adzuna.com/docs/search
- https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
- https://developer.usajobs.gov/tutorials/search-jobs
- https://docs.indeed.com/api-guides/
