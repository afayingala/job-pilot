# JobPilot

A runnable local application for resume-based job discovery and automated applications. No paid model/API key is required. It uses a deterministic resume matcher, public job APIs, employer career pages, SMTP email delivery, a browser form adapter, SQLite history, and Windows Task Scheduler.

## Run

1. Run `Setup.cmd` once if dependencies are not installed.
2. Double-click `Start.cmd`. The dashboard opens at http://127.0.0.1:8765.
3. In Settings, connect your sending email using **Sign in with Google**. This requires one-time Desktop OAuth client registration; follow [GOOGLE_SETUP.md](GOOGLE_SETUP.md). Google tokens are encrypted using Windows DPAPI. The alternative SMTP/app-password method remains available. Test the connection in the dashboard; no email is sent by this test.
4. Click **Find & apply now**. **Search only** discovers jobs and writes drafts without submitting.
5. Run `Install-Schedule.ps1` once in PowerShell to install noon and 5 p.m. Cameroon-time runs. Scheduled runs do not require the dashboard or Codex to be open. Windows must be running, online, and signed into this user. Missed runs start when available; the task requests wake from sleep, subject to Windows power settings. The single task prevents overlapping scheduled instances. If the host timezone changes, reinstall the schedule.

`Run-Now.cmd` runs the worker once from a terminal. The dashboard's pause switch also pauses scheduled submissions and searches.

## Actual automation coverage

- Remote discovery: twelve resume-related Himalayas queries (Cameroon + entry level + UTC+1), Remotive, and configured Greenhouse, Lever and Ashby employer feeds. Responses are cached four hours so noon and 5 p.m. can each receive fresh jobs. Jobs link back to each source. Adding a hosted Lever/Ashby/Greenhouse board URL in Settings automatically selects the proper feed adapter.
- Douala: configured employer career pages are monitored. JSON-LD JobPosting vacancies can enter automatic matching. Unstructured pages are review leads because deadlines and requirements cannot be established reliably. Add employer career URLs in Settings to expand local coverage.
- Email: automatically sends a tailored message and attached resume when a verified employer posting explicitly instructs email applications and an unambiguous application email can be identified. SMTP acceptance is recorded as such; it does not establish the employer opened the message.
- Forms: the browser adapter fills basic contact details, profile links, known location/time zone, cover letters, and resume uploads. It submits only complete forms with an unambiguous submit button. A new confirmation screen is required before recording success. Login/CAPTCHA, legal agreements, required custom answers, videos, and unsupported widgets are queued as blocked rather than guessed or bypassed.
- The browser adapter supports ordinary forms, not every ATS or LinkedIn Easy Apply. This implementation cannot guarantee fully unattended applications across arbitrary websites. An email connection and any required job-site access are real prerequisites.
- Retry protection: a submit attempt with no receipt is **submission_uncertain** and is never automatically resent. The previous SABMA attempt is imported with that status.
- Blocked preparation attempts are retried after 24 hours, using the last attempt time rather than the last discovery time. Saving confirmed profile answers requeues missing-answer applications immediately. User skips remain skipped across rediscovery.
- Reusable answers can be entered under Settings, one `Question = Answer` per line. Exact normalized questions are matched, including accessible labels and native select options. Unknown answers are never generated.
- Auto-apply is enabled as requested. This installation is configured for up to 20 confirmed submissions per run (40 per day), explicitly approved November 11, 2026. No salary minimum has been supplied. Degree completion remains unconfirmed; the expected December 2026 date is used.

## Files

- `profile.json`: resume-derived facts, editable locally.
- `RESUME.pdf`: stable resume copy.
- `settings.json`: source configuration, application limits, SMTP metadata (no password).
- `smtp.secret`: Windows-account-encrypted SMTP password.
- `jobpilot.db`: jobs, runs, outcomes, duplicate protection.
- `drafts/`: tailored text for matched jobs.
- `evidence/`: receipt screenshots for successful form submissions.
- `logs/scheduled.log`: unattended worker output.

Dashboard is bound only to 127.0.0.1, rejects foreign Host headers, and requires a per-process token for mutations. Do not expose it publicly. Source fetches reject private IP addresses and validate redirects. Web content is never executed as agent instructions. External pages can still be unreliable; inspect Needs attention and run history.

## Tests

Run `.venv\Scripts\python.exe -m unittest discover -s tests -v`. Tests use local fixtures and mocked delivery. No test submits to an employer. A live search-only run tests actual source access separately; blocked sources are recorded rather than hidden.

## References

- [Himalayas public API](https://himalayas.app/api)
- [Remotive public API](https://github.com/remotive-com/remote-jobs-api)
- [Playwright Python](https://playwright.dev/python/docs/library)
- [Google app passwords](https://support.google.com/accounts/answer/185833)
