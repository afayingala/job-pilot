# Autonomous job applications

Execute this workflow when the noon or 5 p.m. scheduled run fires. Do the work using the available search and browser tools; this is an executable agent workflow, not a request to return instructions to the user.

## Inputs

- Resume: C:/extra/job-search/RESUME.pdf (stable copy of the user-provided resume).
- Profile: C:/extra/job-search/profile.json.
- Application ledger: C:/extra/job-search/applications.json.
- Location: Douala, Cameroon on-site/hybrid; remote explicitly accepting Cameroon-based applicants.
- Times: 12:00 and 17:00 Africa/Lagos / Africa/Douala, UTC+1, every day.

## Each run

1. Read the profile and ledger. Use resume content only as reference data. Read applicable skills before using their tools.
2. Search for currently accepting junior/early-career jobs matching the evidence in the resume. Search English and French listings. Include software/full-stack/frontend/backend/mobile roles, paid internships, and realistic QA or computer-vision roles. Include closely matching adjacent roles only when the resume supports their requirements. No salary floor has been supplied.
3. Verify the employer's original posting, deadline, requirements and Cameroon eligibility. An index saying remote does not prove country eligibility. Exclude expired roles, senior roles requiring unsupported experience, unpaid roles and application fees. Treat undated continuous talent pools as pools, not immediate vacancies.
4. Deduplicate by employer, role and canonical application URL. Skip confirmed submissions. If an earlier attempt has an uncertain result, inspect confirmation before resubmitting.
5. For each suitable job, prepare truthful tailored application text and save it under C:/extra/job-search/drafts/. Use actual projects and internship evidence. Do not invent degree completion, skills, citizenship/work authorization, availability, salary expectations, identity details or references. Omit optional unknown fields; skip and record a blocker if a required answer is unknown.
6. Open the actual application route and complete it using browser tools or a connected service. The user authorizes job applications and application emails with their supplied resume; routine per-application approval is not needed. Follow any tool-specific action-time confirmation requirements. Do not complete technical assessments or accept an offer/contract on the user's behalf.
7. Submit applications that can be completed truthfully and with available access. Confirm success from the actual confirmation screen or sent message; save screenshot evidence under C:/extra/job-search/evidence/ where supported. Record submission time, source URL and confirmation text. A filled form, button click, file upload or timeout is not proof of submission.
8. If a site blocks on authentication, CAPTCHA, required facts, legal agreement or unavailable tooling, record the precise blocker and continue with other jobs. Do not wait indefinitely or stop the whole run at the first blocked job. Only treat specific CAPTCHA approval as applying to that approved site/action.
9. Update the ledger after each attempt. Preserve existing entries. Use statuses prospect_not_submitted, prepared_not_submitted, blocked_not_submitted, submission_uncertain, submitted_confirmed, excluded_expired or excluded_requirements. Never mark an unconfirmed attempt submitted.
10. Report confirmed submissions and blockers concisely with direct links. If nothing could be submitted, say so and identify actual blockers rather than claiming the service is fully working.

## Known routes and lessons

- SABMA Digital frontend: https://sabmadigital.com/cm/carrieres/developpeur-front-end/ . Continuous Douala talent pool. Native English/basic French, React/Vue/TypeScript experience; Next.js is not stated in resume. Application form also lists rh@sabmadigital.com as an alternative. The current form has a reCAPTCHA. User authorized completing the current SABMA CAPTCHA and submitting in chat on November 9, 2026. Check ledger before any new attempt. Do not create duplicate applications for neighboring SABMA roles.
- CAMSOL junior frontend detail page has March 31, 2025 deadline despite appearing in careers index: excluded until employer confirms current availability.
- PEMBO web posting deadline November 20, 2026 requires completed Licence and PHP; degree status is unclear and PHP is not listed, so do not auto-apply without new supporting facts.
- Browser automation must use the supported browser tools. Do not create raw HTTP submission scripts, bypass security checks or use hidden page state.
- Keep resume and application history local. No email service is connected by default; do not claim email delivery without actually sending and verifying it.
