# Jobref — Progress

> Vertical-specific progress for Jobref. Platform-level infra/architecture
> lives in [`PROGRESS.md`](PROGRESS.md) — read that first if you haven't.

---

## 🎯 NEXT SESSION PRIMARY TASK

None open. Most recent work (Aug 2026, deployed and verified in
production): Jobref made public-ready for community sharing while
Applaut stays private — see "Jobref shared publicly: hub visibility
config + employee active/inactive" below for the full detail. Before
that: a bug fix so session persists through the LVAMO hub (see "Bug fix:
auth pages didn't check for an existing session" further below).

**Seeker dashboard merged into one two-column view + 5-min idle timeout —
deployed (Aug 2026)**: user's explicit follow-up to the "My requests"
page from the previous entry — they didn't want a separate icon/page
after all. That page's content is now the *right* column of the seeker's
dashboard itself (left: companies, a thin `border-right` divider, right:
requests sent), and the standalone page + nav icon are gone entirely.
Separately: any authenticated Jobref session (either user type, wherever
in the app) now auto-logs-out after 5 minutes of no
mouse/keyboard/touch/scroll activity. See "Seeker dashboard: merged
two-column layout + idle timeout" below.

**Status (Aug 2026): the entire referral request lifecycle is live in
production**, built and deployed across one long session — auth through
a decided request, employee-side:

- Auth — both employee-direct and job-seeker-via-LinkedIn registration
  proven end-to-end in production with real data (including a real
  LinkedIn consent-screen signup). `jobref.users` is a single flat table,
  `is_employee` the sole differentiator (migration `0013`).
- `jobref.companies` seeded automatically at employee registration
  (migration `0014`), shown to seekers on their dashboard grouped with a
  referrer count.
- A seeker clicks a company tile → instructions + form →
  `jobref.referral_requests` (migration `0015`), routed to a specific
  employee at that company via a random-among-under-cap algorithm that
  respects each employee's own daily review cap (migration `0016`).
- Seeker-side limits (migration `0017`): one request per UTC day across
  any company, a dashboard note + per-tile lockout when used, a persistent
  "Requested" badge on companies already messaged, no duplicate job link
  when re-requesting a company later.
- The employee opens a routed request (auto-marks `under_review`), sees
  the seeker's info plus two counts (from this seeker, for this job
  posting), then **Accept**s (optionally uploading real evidence of the
  referral to Cloudflare R2) or **Reject**s (a required 150-char response
  to the seeker, with suggested reasons) — migration `0018`.
- Dashboard redesign: profile info lives in a slide-out panel (with real
  editing, everything except email) reached via a top-right icon, leaving
  the main page as just a responsive grid of companies/requests.

Every piece above was pushed, deployed via `deploy.sh` + Cloudflare Pages,
and re-verified against the real production API immediately after (not
just locally, and for the evidence upload specifically, not just the DB
row either — a real object was confirmed sitting in the actual R2 bucket)
— see the dated entries below for the full build log and verification
detail of each one.

**Next up**: nothing notifies a seeker when their request gets decided —
no email, no in-app signal, nothing. That's the natural next feature; see
"Next steps" near the bottom of this file.

---

## Jobref shared publicly: hub visibility config + employee active/inactive (Aug 2026, deployed and verified in production)

User's goal: share Jobref with their community while keeping Applaut
private but still personally usable — not a hard cutoff, a "don't let
people stumble into it" ask. Landed as two independent pieces, both
config-driven rather than a code-level gate, so neither needs a deploy to
adjust going forward.

### 1. Hub visibility via `applaut.application_settings.verticals_enabled`

Rather than hardcoding which vertical cards `frontend/src/pages/Hub.tsx`
(shared, flagged before editing per this session's scoping rules) shows,
it now fetches a `verticals_enabled` setting and only renders cards whose
name is in that comma-separated, lowercase list. Applaut's own
`/applaut/*` routes are completely unaffected — direct URLs still work
exactly as before; this only controls what's *listed* on the hub.

**Reused existing infra rather than building new**: `application_settings`
(id/setting_name/value/description) already existed — built in an earlier
Applaut session (migration `0006`), later moved into the `applaut`
Postgres schema (migration `0012`) — with a public, unauthenticated
`GET /api/v1/applaut/settings/{setting_name}` endpoint and one existing
row (`allow_new_registrations`). Migration `0019` just adds a second row:
`verticals_enabled = 'jobref'`. No new table, no new backend endpoint.

**Fails closed**: if the settings fetch errors for any reason, Hub.tsx
shows no cards at all rather than risk exposing a hidden vertical.
Rendering is also gated on the fetch actually completing (`enabled` starts
`null`, not `[]`) so there's no flash-of-Applaut before the real value
loads.

**Also fixed while in this file** (surfaced by the change, not requested):
the "Open X" card button text was hardcoded to "Open Applaut" for any
`status: 'live'` card — harmless while Applaut was the only live vertical,
wrong now that Jobref is genuinely live too (its badge was still saying
"Coming soon"). Now uses the vertical's own name; Jobref's badge updated
to "Live" to match its actual shipped status.

**To re-enable Applaut on the hub** (for the user personally, or when
ready for others), no deploy needed — just update the row directly:
`UPDATE applaut.application_settings SET value = 'applaut,jobref' WHERE
setting_name = 'verticals_enabled';`

**Verified**: locally via Playwright (hub shows only the Jobref card,
direct `/applaut` nav still fully renders, zero console errors) and again
against the real production site (`www.lvamo.com`) the same way, plus a
direct hit on the live settings endpoint.

### 2. Employee active/inactive, reusing `jobref.users.is_active`

Follow-up to a request to delete a test employee account (the user's own,
"Zalando") and its company row — investigating first surfaced that it had
a real **accepted** referral request against it (with an uploaded evidence
file), from what looked like the user's own second test account. A hard
delete would have cascade-deleted that request. User's decision: build a
proper active/inactive mechanism instead of deleting, so this kind of data
can be hidden without being destroyed.

**Reused existing infra again**: `jobref.users.is_active` (boolean,
default `true`) already existed and was **already enforced** at both
`login()` and `get_current_user()` (`services/auth.py`) — so "an inactive
employee can't log in, and an already-logged-in one gets kicked on their
next request" was already fully built. The originally-proposed new
`User_status` column was dropped as a duplicate once this was found.

**What was actually missing**, now fixed in two places:
- `services/company.py::list_companies()` — now joins to `JobrefUser` and
  filters `is_active = true` before grouping, so both the companies
  listing itself and each `referrer_count` reflect only active employees.
  A company with at least one other active employee still shows normally
  — verified with two employees at one company: deactivating one dropped
  `referrer_count` from 2→1 and kept the company listed; deactivating the
  second made the company disappear entirely.
- `services/referral_request.py::_find_eligible_referrer()` — the routing
  algorithm now excludes inactive employees too. This wasn't explicitly
  asked for but is a real gap the same feature exposed: without it, an
  inactive employee could still be randomly assigned a new referral
  request despite being unable to log in to review it.

**No new migration** — pure code change, `is_active` already existed and
already had the right default.

**Verified locally** (real, not mocked): registered two employees at one
company, confirmed `referrer_count: 2`; deactivated one via direct SQL,
confirmed `referrer_count: 1` and a login attempt for that account
returned `403 "Account disabled"`; deactivated the second, confirmed the
company fully disappears from `/companies` and the routing query returns
zero eligible employees. Cascade-delete of the test accounts confirmed
clean afterward. `tsc --noEmit` clean (no frontend files touched).
Applaut regression clean.

**Deployed and re-verified in production**: `bash deploy.sh` ran clean
(no migration this round). The original test employee
(`vsvedantham@gmail.com`, company "Zalando") was set `is_active = false`
directly in production rather than deleted — its one accepted referral
request (with real R2 evidence) is preserved, not cascade-deleted. Confirmed
via direct DB query that the live `/companies` query now excludes it
(0 rows — it was the only company registered in production so far).

**Not yet built**: no admin UI for toggling `is_active` — both changes
above were applied via direct SQL through an SSH session, same as the
`verticals_enabled` row. Worth a real admin surface if this needs to
happen more than occasionally.

---

## Older: employee registration form settled (Aug 2026, deployed)

**Employee registration form is now fully settled (Aug 2026, deployed) —
three rounds same day, all live:**

1. New required field, "How many referral requests can you review per day?"
   (wording tweaked from "view" → "review" later the same day, copy-only,
   field name unchanged)
   (`Max 5`/`5-10`/`10-20`/`No Cap`), migration `0010`.
2. Job Seeker disclaimer reworded to general platform-policy phrasing.
3. The old "I can refer other candidates" checkbox removed entirely —
   referral capacity is now asked directly: "How many referrals can you do
   in a…" with a Week/Month segmented toggle, then the *same* bucketed
   scale as #1 above (not a raw number). `can_refer`/`refer_count` dropped
   from the schema, migration `0011`.

All verified live in production with real API calls (`201`/`422` on
valid/missing data) and against the live frontend (`www.lvamo.com`) —
zero checkboxes left in the form, both toggle buttons functional, Applaut
regression clean each round. See "Referral capacity" and "New employee
field + disclaimer reword" sections below for full detail.

**Still outstanding, unchanged**: nobody has completed a real *job-seeker*
registration through the actual LinkedIn consent screen and final form
submission — only the OAuth handshake itself (real) and a mocked-token
submission have exercised that path. The employee path is fully verified
end-to-end in production with real data (both before and after this UX
change). **Next session**: one real seeker signup at
`https://www.lvamo.com/jobref/register` (Job Seeker card) to close this out.

---

## Status: Live in production — auth, companies, the full referral request flow (routing, seeker limits) and employee decisions (accept/reject, evidence upload) all deployed, Aug 2026

## Bug fix: auth pages didn't check for an existing session (Aug 2026, deployed and verified in production)

User's report: log in, click the LVAMO logo or "Back to LVAMO" (both go
to `/`, the shared hub — not touched, out of scope), then click "Jobref"
from there — landed back on the Get-started/Sign-in landing page instead
of the dashboard, despite still being genuinely logged in the whole time
(token untouched, `useJobrefAuth()`'s session check would have confirmed
it). "The earlier login should persist" was the exact, correct
expectation.

**Root cause**: `pages/Jobref.tsx` never called `useJobrefAuth()` at
all — it's a static landing page with no auth awareness whatsoever, so it
always rendered the logged-out CTAs regardless of session state. Checking
`Login.tsx`/`Register.tsx`/`RegisterComplete.tsx` for the same pattern
found all three had the identical gap (each only destructured the
*action* — `login`/`register` — from the context, never `user`), which
matters beyond just this bug report: without the fix, an already-
logged-in seeker could land on `Register.tsx`/`RegisterComplete.tsx` (via
a stray bookmark, a second LinkedIn attempt, etc.) and genuinely create a
second account.

**Fix, identical shape in all four**: `if (loading) return null; if
(user) return <Navigate to="/jobref/dashboard" replace />` before the
existing render logic — `Login.tsx`/`Register.tsx` both already had a
local `loading` state (form-submission spinner), so the context's own
`loading` is aliased to `authLoading` to avoid a name collision.

**Verified locally** (real, not mocked): full real-browser Playwright
run of the exact reported sequence — logged in as a seeker, clicked
"Back to LVAMO," landed on the hub, clicked "Jobref," confirmed the final
URL is `/jobref/dashboard` and the actual dashboard content is genuinely
rendered (not a flash of the landing page — checked via a screenshot at
the intermediate moment too, since an initial loose text-match check
raised a false alarm that turned out to just be dashboard copy
coincidentally containing the words "get started"). Also confirmed direct
navigation to `/jobref/login` and `/jobref/register` while already logged
in both correctly redirect to the dashboard instead of showing the form.
Zero console errors. `tsc --noEmit` clean.

**Deployed and re-verified in production**: `bash deploy.sh` on the VM
(pure frontend fix — migration output showed "no change"). Confirmed the
new Cloudflare Pages build was live (bundle contains the landing-page
copy), and both `jobref`/`applaut` health checks returned `200`. Then ran
a real end-to-end Playwright check against `www.lvamo.com` itself,
reproducing the user's exact reported steps: registered a real employee
(`prod-persist-emp@example.com`) via the live API, logged in for a real
token, loaded the dashboard, clicked "Back to LVAMO," landed on
`https://www.lvamo.com/`, clicked "Jobref," and confirmed the URL went
straight to `https://www.lvamo.com/jobref/dashboard` with the dashboard
genuinely rendered and zero console errors. Test data (the prod employee
row) deleted afterward.

## Seeker dashboard: merged two-column layout + idle timeout (Aug 2026, verified locally)

User's direct follow-up, same session as the "My requests" page below —
explicit reversal of that choice: no separate icon, no separate page.
"Referral requests sent" moves onto the seeker's actual homepage, as a
second column beside "Companies available for referrals," divided by a
thin line. Separately, unrelated: a 5-minute idle timeout across the
whole authenticated session.

**Layout**: `pages/Dashboard.tsx`'s seeker branch is now
`display: flex; flex-wrap: wrap` with two children, each
`flex: 1 1 420px` — companies on the left (`border-right: 1px solid
var(--border)` for the divider, `padding-right`/`margin-right` for
symmetric spacing), sent requests on the right (the exact card markup
`MyReferralRequests.tsx` used, moved in directly — read-only, no
`Link`/click affordance, since these are the seeker's own past
submissions, not something to act on). No new fetch needed:
`myRequests` was already being fetched unconditionally for every logged-
in user (it back the companies badges/lockout logic too), so the second
column just renders data the component already had.

**Why `flex-wrap` + `minmax`-style basis, not a media query**: same
reasoning as every other responsive layout in this codebase — at
`flex-basis: 420px` each, two columns fit side by side above roughly
900px combined width and wrap to a single stacked column below it,
without an explicit breakpoint. The divider (`border-right` on the left
column) doesn't disappear when stacked on mobile — it just reads as a
subtle accent line on the right edge of the companies panel instead of a
true mid-page divider. Decided that was an acceptable trade-off rather
than reaching for a `@container` query (which would still be a
breakpoint in spirit, just container- instead of viewport-relative) to
make it vanish exactly on wrap.

**Removed entirely**: `pages/MyReferralRequests.tsx`, the `/jobref/requests`
list route (`/jobref/requests/:id`, the *employee's* per-item detail page,
is untouched — different route, no collision), `components/Icons.tsx`'s
`SentIcon` (now unused), and the `IconLink` helper in `Dashboard.tsx`
(also now unused, since the top-right icon row is back down to just
Profile + Logout for every user type).

**Idle timeout**: `context/AuthContext.tsx` — a `useEffect` that arms
only while `user` is truthy, listens for
`mousemove`/`mousedown`/`keydown`/`scroll`/`touchstart` on `window`, and
resets a 5-minute `setTimeout` on each one; firing clears the token and
`setUser(null)`. No explicit navigation call needed — `JobrefProtectedRoute`
already redirects to `/jobref/login` on its own once `user` is null, and
the provider wraps the *entire* app (both user types, every route,
protected or not), so this is a true session-wide idle timer, not
per-page. Scoped to Jobref only for this pass — Applaut has its own
separate `AuthContext.tsx` and wasn't touched.

**Verified locally** (real, not mocked): full real-browser Playwright
check of the merged dashboard at both 1440px and 390px — companies (with
the daily-limit note and "Requested"/lockout state) and "Referral requests
sent" both render in one view, zero console errors either viewport,
confirmed the old "My requests" icon is entirely gone. Idle timeout
verified without an actual 5-minute wait, via Playwright's
`page.clock.install()`/`fastForward()` against the component's real
scheduled `setTimeout` (not a fake one): 2 minutes idle → a real
`mousemove` event (resets the timer) → another 2 minutes → token still
present; then 5:01 of continuous idle from that reset → token cleared;
reloading afterward correctly landed on `/jobref/login`. `tsc --noEmit`
clean. Applaut/Jobref regression clean. Cascade delete confirmed clean.

**Deployed and re-verified in production**: no migration needed (pure
frontend + minor API-usage change). Registered a real employee + seeker
against prod, submitted a real request, then confirmed the live page at
`www.lvamo.com/jobref/dashboard` shows both columns together with the
real submitted request ("Prod Layout Co", "Pending review", the exact
message sent) beside the companies list (locked, "Requested" badge) —
screenshot-verified, zero console errors, confirmed the old "My requests"
icon is entirely absent from the live page (not just the local build).
Test data cleaned up, Applaut regression clean.

## Seeker "My requests" page (Aug 2026, verified locally — superseded same session, see entry above)

Follow-up to employee actions above — the seeker side of the same
lifecycle: a page listing everything they've sent and what happened to
it, since requests now actually reach a real outcome (accepted/rejected)
worth checking back on.

**Backend**: no new endpoint — `GET /referral-requests` already
dual-purposed to return a seeker's own sent-request history (built
earlier for the companies-badge/daily-limit-note logic, see "Companies
list on the seeker dashboard"). Extended `ReferralRequestInboxItem` (the
shared list-item schema) with `rejection_reason`/`evidence_file_name` so
a seeker can see *why* they were rejected directly from the list, without
needing the employee-only detail endpoint (`GET .../{id}`, which also has
the side effect of marking a request `under_review` — not something a
seeker's own read should ever trigger).

**Frontend**: new `pages/MyReferralRequests.tsx` (route `/jobref/requests`
— distinct from `/jobref/requests/:id`, the employee's per-item detail
page; no actual routing collision, just a shared path prefix), reached
via a new icon on the seeker dashboard (`components/Icons.tsx`'s
`SentIcon`, a paper airplane — themed around "requests you've sent" rather
than a generic list glyph), positioned before Profile/Logout in the same
top-right icon row, seeker-only. Same status pill styling
(`STATUS_COLOR`/`STATUS_LABEL` from `constants.ts`, already shared with
the employee inbox) — accepted shows a green confirmation banner,
rejected shows the employee's response in a red banner, pending/under
review just show the status pill with no extra banner. Read-only: no
buttons, no state changes — this page only reports.

**Verified locally** (real, not mocked): seeded one seeker, backdated two
of their three requests by a day each to get around the once-per-day
limit (matching the same technique used to verify that limit originally),
had the employee accept one, reject one, and merely open (not decide) the
third. Full real-browser Playwright check of `/jobref/requests`: all
three rendered correctly — "Accepted" (green, confirmation text),
"Rejected" (red, showing the exact reason the employee sent), "Under
review" (no banner) — newest-first, zero console errors. Confirmed the
new icon is entirely absent from the employee dashboard (seeker-only, as
intended). `tsc --noEmit` clean. Applaut/Jobref regression clean. Cascade
delete confirmed clean.

**Deployed and re-verified in production**: no migration needed (pure
API/frontend addition). Real end-to-end run against prod: registered an
employee + seeker, submitted a real request, had the employee reject it
with a real reason, then confirmed the seeker's own `GET
/referral-requests` correctly returned `rejection_reason: "Prod
verification reject reason"` — the exact text the employee sent. Cloudflare
Pages auto-rebuilt — confirmed both "My referral requests" and "Accepted
and sent for referral" strings present in the live built JS bundle. Test
data cleaned up, Applaut regression clean.

## Employee actions on a referral request (Aug 2026, verified locally)

Follow-up to the employee inbox — user's explicit spec: remove the CV/
cover-letter/job links from the inbox tile, make the tile itself
clickable into a detail page. Opening it moves the request to "under
review." The detail page shows the seeker's info plus two counts (from
this seeker, for this job posting), then two decisions: **Accept**
("Request accepted and sent for referral" — optionally with uploaded
evidence of the referral) or **Reject** (a required 150-char response to
the seeker, with suggested reasons).

**Status lifecycle**: `pending_review` → `under_review` (automatic, on
first open) → `accepted` or `rejected` (terminal, employee decision).
Migration `0018` widens the single-value `status` `CHECK` constraint from
migration `0016` to allow all four (same widen-the-constraint pattern used
for `ReferralViewCapacity` back in migrations `0010`/`0011`).

**New columns**: `rejection_reason` (`VARCHAR(150)`, required iff
`status = 'rejected'` — DB `CHECK` biconditional, same pattern as the
seeker profile's `notice_join_date`-iff-`serving_notice` rule from
earlier in this schema), `evidence_r2_key` + `evidence_file_name` (both
set together iff evidence was shared, and only when `status = 'accepted'`
— also DB `CHECK`-enforced). `reviewed_at` (already existed, unused since
migration `0016`) is now finally set — on the *decision* (accept/reject),
not on the "opened" transition, which is what `under_review` itself
signals.

**The two counts**: `job_posting_request_count` is every request (from
any seeker) sharing this exact `(company_name, job_link)` pair;
`seeker_request_count` is every request this specific seeker has sent
*this specific employee* (not a global count across all employees at the
company — the more useful signal when an employee is asking "have I seen
this person before").

**Evidence upload reuses Applaut's existing R2 client** (`app.core.
storage`, shared/generic infra, imported without modifying it) and its
exact graceful-degradation convention for when R2 isn't configured
(`services/resume.py`'s `if settings.r2_bucket_name: upload_file(...)
else: r2_key = f"local/{r2_key}"`). **Correction to an earlier note in
this entry**: R2 *is* actually configured in production (real
credentials in `.env.production` — verified properly this time, by
checking value *lengths* rather than a `grep -o` that could never have
shown a value either way, which is what produced the wrong "empty
everywhere" claim originally). Confirmed for real: a genuine `POST
.../accept` with an evidence file in production landed an object in the
actual R2 bucket (`head_object` confirmed it, `ContentType: image/png`,
correct size) — not just a DB row with a `local/`-prefixed key. Deleted
that test object afterward. **Local dev only** is the `local/`-prefix
case — `R2_*` vars are genuinely empty there (confirmed by length, not
just by presence of the line).

**Backend**: `GET /referral-requests/{id}` (the "open = mark under
review" side effect, employee-only, 404 if not routed to the caller —
same `_get_owned_request` ownership check reused by all three new
endpoints so none of them can read/act on someone else's inbox item),
`POST /referral-requests/{id}/accept` (multipart, optional `evidence`
file — JPEG/PNG/WebP/PDF, 5 MB cap, same limits as Applaut's resume
upload), `POST /referral-requests/{id}/reject` (JSON, `reason` 1-150
chars). Both decision endpoints `409` if the request is already
`accepted`/`rejected` — no re-deciding.

**Frontend**: Dashboard.tsx's inbox tiles dropped the Job posting/CV/
Cover letter links, tile itself is now a `Link` to
`/jobref/requests/:id` (new route, `frontend/src/App.tsx` — flagged and
confirmed before editing, same as the last two route additions). New
`pages/ReferralRequestDetail.tsx`: seeker info + both counts, and — while
undecided — an Accept/Reject choice that branches into the evidence
Yes/No prompt (Yes reveals a file input) or the reject form (a live
150-char counter plus four clickable suggestion chips that fill the
textarea, editable after). New `constants.ts` holds a shared
`STATUS_LABEL`/`STATUS_COLOR` lookup (pending/under-review render as
warn-colored, accepted success-colored, rejected danger-colored) — reused
by both Dashboard.tsx and the new detail page rather than duplicated.

**A real bug caught while wiring the upload**: `jobref/api/client.ts`'s
axios instance hardcodes `Content-Type: application/json` as a default
header, which silently breaks a `FormData` body (multipart needs a
browser-computed boundary in the header, which only happens if
`Content-Type` is left unset). Fixed in the existing request interceptor
— deletes the header when `config.data instanceof FormData`. Caught this
before it ever reached a live test, not after.

**Verified locally** (real, not mocked): seeded 1 employee + 3 seekers, 2
of them requesting the *same* job link at the same company (to produce a
real `job_posting_request_count` of 2) — opening one via `GET .../{id}`
correctly flipped it to `under_review` (idempotent on a second open,
counts correct: 2 for the shared job posting, 1 for that seeker). Reject
→ `200`, correct `rejection_reason` stored, re-rejecting the same
request → `409`; over-length reason → `422`. Accept without evidence →
`200`, `evidence_file_name: null`. Accept **with** a real multipart file
upload → `200`, DB confirmed `evidence_r2_key` correctly prefixed
`local/...` and `evidence_file_name` set. Full real-browser Playwright
flow twice over (once for accept-with-evidence, once for reject): dashboard
tile → detail page (status visibly "Under review" on load) → evidence
Yes → file picked → "Accepted" screen showing the evidence filename; and
separately, Reject → suggestion chip clicked → fills textarea → "Rejected"
screen showing the exact response sent. Zero console errors both times.
Confirmed the CV/cover-letter links are gone from the dashboard tile
itself. `tsc --noEmit` clean. Applaut/Jobref regression clean. Cascade
delete confirmed clean.

**Not yet done**: not deployed — committed locally pending go-ahead (see
banner at the top of this file). Evidence files can't actually be
downloaded/viewed anywhere yet (only the filename is shown as
confirmation) — deliberately out of scope until R2 is actually
configured, since a download flow would be untestable either way right
now.

## Seeker request limits (Aug 2026, verified locally)

User's explicit spec: 1 referral request per seeker per day globally, a
badge on companies already requested, a dashboard note explaining the
once-a-day reset ("after 00:00"), and — when re-requesting the same
company on a later day — the job link must differ from any used there
before.

**Two independent rules, both enforced server-side in
`services/referral_request.py::create_referral_request`, checked before
the existing routing/capacity logic**:
1. **One request per seeker per UTC calendar day, any company** — `429
   Too Many Requests` once hit (chose 429 over 409 deliberately: this is
   a rate limit, not a resource-state conflict — the company-capacity
   case from the earlier routing work stays `409`, keeping the two
   distinct). Checked via a live `COUNT` on `created_at::date = today`,
   same self-resetting-at-UTC-midnight approach as the employee-capacity
   check.
2. **No repeat `(seeker, company_name, job_link)`** — `409` with a message
   naming the exact reason. Backed by a genuine DB-level `UNIQUE` index
   (migration `0017`) as well as the application check, so a race between
   two near-simultaneous requests can't slip through.

**A real Postgres wall hit while building #1's DB backstop**: tried adding
a matching `UNIQUE` index on `(seeker_user_id, created_at::date)` too, but
Postgres rejected it — `functions in index expression must be marked
IMMUTABLE`. A `timestamptz::date` cast depends on the session's `timezone`
setting, so Postgres classifies it `STABLE`, not `IMMUTABLE`, and won't
allow it in an index expression regardless of how deterministic the
result actually is in practice (this DB's session timezone is confirmed
`UTC`, verified via `SHOW timezone`). The usual workaround is a custom SQL
function explicitly marked `IMMUTABLE` — decided against introducing one
for this: it's a new kind of schema object nothing else in this codebase
uses, just to backstop a rule the application layer already enforces
correctly. **Rule #1 has application-level enforcement only, no DB-level
backstop** — a real asymmetry worth knowing if this code is touched again;
rule #2 has both.

**Backend**: `GET /api/v1/jobref/referral-requests` (previously
employee-inbox-only) is now genuinely dual-purpose — a seeker calling it
gets their own sent-request history (new `list_my_requests()`, symmetric
to `list_inbox()`), reusing the same `ReferralRequestInboxItem` response
shape for both audiences.

**Frontend**: `api/referralRequests.ts`'s `listReferralInbox` renamed to
`listMyReferralRequests` (both types now call the same function).
Dashboard.tsx: a warning-colored note above the companies grid, shown only
once the seeker has sent today's request, naming the reset moment via
`nextUtcMidnight().toLocaleString()` — computed as the next UTC-midnight
instant from *now*, rendered in the browser's own local timezone rather
than making the seeker do UTC math. Every company tile becomes a plain
(non-clickable) `div` instead of a `Link` while locked, with reduced
opacity and a "Locked until tomorrow" subtitle. Independently, any company
the seeker has ever messaged gets a second small "Requested" badge
stacked under the referrer-count badge — this persists across days,
separate from the daily lockout state.

**Verified locally** (real, not mocked): backend — 1st request today →
`201`; 2nd request same day to a *different* company → `429` with the
exact message; backdated the first request's `created_at` by a day via
direct DB update to simulate "yesterday," then confirmed re-requesting
the same company with the *same* job link → `409`, and with a *different*
job link → `201`. `GET /referral-requests` as a seeker confirmed returns
their own history (not another seeker's). Full real-browser Playwright
flow: dashboard before any request shows normal tiles, no note; after
sending one, screenshot confirms the note (with a real localized
timestamp), both companies greyed out and non-clickable
("Locked until tomorrow"), and the messaged company alone carrying the
"Requested" badge. Zero console errors. `tsc --noEmit` clean.
Applaut/Jobref regression clean. Cascade delete confirmed clean.

**Deployed and re-verified in production**: migration `0017` ran clean.
Re-ran the exact same sequence against the real prod API — 1st request
→ `201`, 2nd same day (different company) → `429`; backdated the first
request a day, same job link → `409`, different job link → `201`; a
seeker's own `GET /referral-requests` correctly returned only their own 2
requests. Cloudflare Pages auto-rebuilt — confirmed both "Locked until
tomorrow" and the note's exact wording present in the live built JS
bundle. All test data cleaned up, cascade confirmed clean. Applaut
regression clean.

## Dashboard redesign: profile panel + PC layout (Aug 2026, verified locally)

User's observation: the dashboard's old layout (role pill + welcome +
domain, then a full profile card, then the companies/inbox list below it)
worked fine on mobile but wasted a lot of horizontal space and looked
sparse on desktop. Explicit request: profile info into a slide-out panel
behind a top-right profile icon (plus a logout icon beside it), leaving
the main page down to just two things — companies (seeker) or referral
requests (employee) — with an edit option in the panel for everything
except email, and it needed to look good on both PC and mobile.

**Design calls made**:
- **Didn't touch `components/BrandedPage.tsx`** (shared across verticals,
  flagged out-of-scope) — the new top-right icon bar and the slide-out
  panel are both `position: fixed`, so they sit correctly regardless of
  BrandedPage's own centered-flex layout, entirely from within
  Dashboard.tsx/a new Jobref-owned component. No shared file needed
  editing this time.
- **Responsive grid, not a breakpoint** — the companies/inbox lists use
  `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`, which
  naturally renders 1 column on mobile and multiple on wide screens with
  zero `@media` queries, matching the project's existing preference for
  flexbox/grid reflow over explicit breakpoints (same convention already
  used for the employee/seeker registration cards).
- **Hand-rolled SVG icons** — no icon library exists in this project's
  dependencies; adding one for two icons wasn't worth it, so
  `components/Icons.tsx` has small inline SVGs (profile, logout, close).
- **Editing scope: everything except email** — read literally. Reuses
  `EmployeeDetails`/`SeekerDetails` (the same nested schemas registration
  already validates with) inside a new `ProfileUpdate` schema, so the edit
  form gets the exact same conditional validation (e.g. `notice_join_date`
  required-iff-`serving_notice`) for free rather than re-implementing it.
- **Editing an employee's company name/URL also updates their
  `jobref.companies` row** — that row was seeded once at registration
  (see the companies-gathering entry below); without this sync, editing a
  profile would silently make the seeker-facing companies list stale.
- **Panel always mounted, `transform`/`opacity` toggled** — not
  conditionally rendered — so the CSS slide-in/fade transition actually
  has something to animate from/to.

**Backend**: `ProfileUpdate` schema (`schemas/auth.py`) — `first_name`,
`last_name`, `phone`, `domain` always required, plus exactly one of
`employee`/`seeker` (reusing `EmployeeDetails`/`SeekerDetails`), matching
the authenticated user's own type — enforced in the new
`services/auth.py::update_profile()` (`400` if the wrong/missing one is
sent). New `PATCH /api/v1/jobref/auth/me`, returns the same
`JobrefUserResponse` shape `/me` already does.

**Frontend**: `api/auth.ts` (+`ProfileUpdatePayload`, +`updateProfile()`),
`context/AuthContext.tsx` (+`updateProfile` in the context, updates `user`
state from the response). New `components/ProfilePanel.tsx` (view mode +
edit mode, reusing the exact field/label style vocabulary already
established in `Register.tsx`/`RegisterComplete.tsx`) and
`components/Icons.tsx`. `pages/Dashboard.tsx` rewritten: fixed top-right
icon bar (profile + logout), page heading, grid-based list, `ProfilePanel`
mounted at the bottom. No new route — the panel is part of the dashboard
page, not a separate URL.

**Verified locally** (real, not mocked, full real-browser flow across
viewports): desktop (1440×900) — companies grid correctly shows 3 columns
for 3 seeded companies; profile panel slides in cleanly over a dimmed
backdrop; clicked "Edit profile," changed the domain field, saved, panel
returned to view mode showing the new value, confirmed via a second
`/me` fetch under the hood (the `AuthContext` update). Mobile (390×844) —
single-column grid, icon bar fits without crowding the logo, panel takes
`min(400px, 100vw)` so it's fully readable rather than cramped. Employee
side — same panel with employee-specific fields (company name/working
since/careers URL/both capacity dropdowns/Week-Month toggle), pre-filled
correctly. Logout icon confirmed to actually clear the token and redirect
to login (only reachable once the panel itself is closed — by design, it
sits under the panel while open, same as any drawer). Found and fixed one
real bug from screenshots: the profile view accidentally
`text-transform: capitalize`'d the email address (inherited from the old
status-row styling) — `ViewRow` now only capitalizes where asked
(`current_job_status`), not by default. Zero console errors throughout.
`tsc --noEmit` clean. Applaut/Jobref regression clean. Cascade delete
confirmed clean across all three jobref tables after test cleanup.

**Deployed and re-verified in production**: no migration needed (pure
API/frontend change). Real employee registration + a real `PATCH
/auth/me` against the live API → `200` with the edited values reflected
immediately; `jobref.companies` confirmed updated to match the edited
company name/URL via direct DB query. Cloudflare Pages auto-rebuilt —
confirmed both "Edit profile" and "can't be changed" strings present in
the live built JS bundle. Test data cleaned up, Applaut regression clean.

## Employee referral inbox + routing (Aug 2026, verified locally)

Follow-up to the referral request flow below — user's explicit spec:
`jobref.referral_requests` needed a `From` (seeker), `To` (referrer) and a
`status`, plus a routing rule they defined precisely: if 3 employees at a
company each set a daily cap of 5, that's 15 possible requests/day for the
company; allocate the referrer **randomly** among employees, track how
many each has received, and exclude an employee once their own threshold
is hit **for that day**.

**Migration `0016`** (table had zero rows, so straight `ADD COLUMN ...
NOT NULL` with no backfill needed): `to_user_id` (FK → `jobref.users`,
`ON DELETE CASCADE`, indexed), `status` (`VARCHAR(30)`, single-value CHECK
`'pending_review'` for now — same ALTER-to-add-a-value pattern already
used for `ReferralViewCapacity` in migrations `0010`/`0011`, ready to grow
once employee actions exist), `reviewed_at` (nullable, unset by anything
yet — a "timestamp you'll want later" per the user's own prompt, ready for
whenever an accept/decline action gets built).

**Routing algorithm** (`services/referral_request.py`):
1. Find every employee at the target company (via `jobref.companies`,
   keyed by `name`+`careers_url`, same grouping key the `/companies`
   listing uses).
2. For each, compute their effective daily cap from
   `daily_referral_view_cap`'s bucket — **the upper bound of the range**
   (`up_to_5`→5, `5_to_10`→10, `10_to_20`→20, `no_cap`→unlimited). Matches
   the user's own example verbatim (`up_to_5` = "5 reviews per day").
3. Count that employee's `jobref.referral_requests` rows created **today**
   (`func.date(created_at) = UTC today`) — computed live, not a separately
   maintained counter, so it self-resets at UTC midnight with no reset job.
4. Exclude anyone at or over their cap; **randomly** pick one of whoever's
   left.
5. If nobody's left (whole company at capacity) or the company has no
   employees at all, reject with `409` (capacity) — the seeker's existing
   generic error-banner handling on `ReferralRequest.tsx` already
   surfaces this with no frontend changes needed.

**Backend**: `GET /api/v1/jobref/referral-requests` (new) — employee-only
(`403` for seekers, mirroring the existing `POST`'s seeker-only `403` for
employees), returns that employee's routed requests newest-first.
`POST /referral-requests`'s payload/response shape is unchanged; routing
just happens internally now instead of a hardcoded/absent referrer.

**Frontend**: Dashboard.tsx gets a second type-gated section, symmetric to
the seeker's companies list — `isEmployee && ...` renders "Referral
requests": a card per request (seeker name, timestamp, a status pill,
the message in quotes, and job posting / CV / cover letter links). No new
route or page needed — reuses the exact same dashboard-hosts-type-specific-
content pattern as the companies list. `STATUS_LABEL` is a lookup (one
entry today) rather than inline text, so adding future statuses is a
one-line change.

**Verified locally** (real, not mocked): registered 3 employees at the
same company, each with `daily_referral_view_cap: up_to_5`; submitted 15
referral requests from one seeker — all `201`, and a DB query confirmed an
exact 5/5/5 split across the three employees; the 16th request correctly
`409`'d ("reached its daily referral capacity"). Employee inbox endpoint
confirmed newest-first ordering and seeker-blocked (`403`). Full
real-browser flow via Playwright: seeker submits a request through the
real UI → employee's dashboard shows it under "Referral requests" with
correct name/message/status/links, zero console errors, screenshot
confirms the visual matches the rest of the app. `tsc --noEmit` clean.
Applaut/Jobref regression clean. All test data cleaned up (cascade delete
confirmed no orphans).

**Deployed and re-verified in production**: migration `0016` ran clean.
Re-ran the exact same routing test against the real prod API — 3
employees at one company, each `daily_referral_view_cap: up_to_5`, 15
submitted requests all `201` with a confirmed 5/5/5 split via direct DB
query, 16th request correctly `409`'d. Employee inbox endpoint confirmed
5 items, newest-first field shape correct; seeker calling it → `403`.
Cloudflare Pages auto-rebuilt — confirmed both "Referral requests" and
"Pending review" strings present in the live built JS bundle. All test
data (4 users, 15 referral requests) deleted afterward, cascade confirmed
clean. Applaut regression clean.

Still not built: any employee action on a request (accept/decline/mark
reviewed) — `reviewed_at` and the single-value `status` CHECK are both
ready for that, but no endpoint sets them yet.

## Referral request flow (Aug 2026, verified locally)

Follow-up to the companies list above — user's request: clicking a
company tile should open a page with instructions (visit the careers
page, find a matching posting, tailor CV/cover letter, fill in the form)
and a form (first/last name, job posting link, CV + cover letter Google
Drive links, a 150-char message to the referrer). Explicit go-ahead given
to improvise the rest.

**Design calls made**:
- **New table, not a FK into `jobref.companies`** — `jobref.referral_requests`
  snapshots `company_name`/`company_careers_url` at submission time rather
  than pointing at a specific `jobref.companies` row. That table has one
  row per employee (no dedup — see the companies-gathering entry below)
  and the grouped `/companies` listing the tile comes from doesn't expose
  individual row ids, so there's no single stable "company" to point at
  yet, and no routing-to-a-specific-employee logic exists either (a real
  design question, deliberately not answered here — see "Not yet
  designed" below).
- **CV and cover letter as two separate fields**, not one combined link —
  the ask listed "CV and cover letter" as two documents; two separate
  Google Drive link fields matches how `cv_drive_link` already works
  elsewhere in this app (one link per document) rather than introducing a
  single-shared-folder convention that doesn't exist anywhere else.
- **First/last name prefilled from the seeker's own profile, still
  editable** — asked again per the spec (not silently reused) in case
  someone wants a different/more formal name to appear to the referrer,
  but prefilling removes the friction of retyping it.
- **Message required, hard-capped at 150 chars** both client-side (a live
  `n/150` counter, input truncated as you type past the limit) and
  server-side (Pydantic `max_length` + a `VARCHAR(150)` column — no DB
  CHECK needed beyond the column's own length limit, unlike the enum-style
  fields elsewhere in this schema).
- **Submission restricted to job seekers at the API level** — unlike the
  read-only `/companies` endpoint (left open to any authenticated user
  since it's harmless to read), this write endpoint 403s if an employee's
  token calls it. A referral request only makes sense coming from a
  seeker.

**Backend**: migration `0015` creates `jobref.referral_requests`
(`seeker_user_id` FK `ON DELETE CASCADE`, the two company fields, name
fields, `job_link`, `cv_drive_link`, `cover_letter_drive_link`, `message`).
New `models/jobref_referral_request.py`, `schemas/referral_request.py`,
`services/referral_request.py`, `api/v1/routers/referral_requests.py`
(`POST /referral-requests`, 201, employee → 403).

**Frontend**: Dashboard.tsx's company tiles are now themselves the link
(the standalone "Careers page ↗" link is gone, replaced with a "Tap to
request a referral" hint) — `to=/jobref/refer?company=&careers_url=`,
same query-param pattern as `Register.tsx`'s `?as=employee`. New
`pages/ReferralRequest.tsx`: numbered instructions list (step 1 is a real
link to the careers page), the form, a success screen ("Request sent")
replacing the form in place rather than an abrupt redirect, and a
defensive empty-params error state (mirrors `RegisterComplete.tsx`'s
"start over" pattern) if the page is reached without a company selected.

**Touched `frontend/src/App.tsx`** (shared/out-of-scope file) to register
the new `jobref/refer` route — flagged first, explicit go-ahead given
before editing; the change itself is a single mirror of the existing
`jobref/dashboard` route entry.

**Verified locally** (real, not mocked, full real-browser flow via a
small Playwright driver script): backend — unauthenticated → `403`;
employee token → `403 "Only job seekers can submit referral requests"`;
message > 150 chars → `422`; valid seeker submission → `201`, row
confirmed in `jobref.referral_requests` with all fields correct. Frontend
— logged in as a seeker, dashboard confirmed zero standalone "Careers
page" links remain, clicked a company tile, landed on the request page
with instructions + form, first/last name confirmed prefilled from the
seeker's profile, filled and submitted the form, landed on the "Request
sent" confirmation screen, zero console errors throughout. Deleting the
seeker's user row cascaded to delete their referral request too — no
orphans. `tsc --noEmit` clean. Applaut/Jobref regression clean. All test
data cleaned up afterward (local DB + temp script files).

**Not yet designed** (explicitly out of scope for this pass, same
reasoning as the companies-gathering table's own "not yet designed" note):
how a referral request actually reaches an employee to act on (no
employee-facing inbox/notification exists yet), and whether/how multiple
employees at one company get deduplicated into a single routable
"company" entity. Both are real product questions for whenever the
referral-matching feature gets designed properly.

**Deployed and re-verified in production**: migration `0015` ran clean.
Confirmed `403` for both unauthenticated and employee-token requests
against the real prod API. Full real end-to-end write: minted a
registration token via the actual prod backend container (same technique
used throughout this session for testing the seeker path without the real
LinkedIn handshake — not the same as mocking LinkedIn's own API), real
seeker registration → `201`, fetched `/companies` as that seeker, POSTed a
real referral request → `201`, DB row confirmed correct via direct query.
Cloudflare Pages auto-rebuilt — confirmed both "Tap to request a referral"
and "Request a referral at" strings present in the live built JS bundle.
All test data (2 users, 1 referral request) deleted afterward, cascade
confirmed clean. Applaut regression clean.

## Companies list on the seeker dashboard (Aug 2026, verified locally)

Follow-up to the companies-gathering step below — user's request: show
`jobref.companies` to job seekers on their dashboard, under a heading like
"Companies available for referrals", improvising the rest.

**Backend**: new `GET /api/v1/jobref/companies` (`api/v1/routers/
companies.py`, `services/company.py`, `schemas/company.py`) — grouped by
`(name, careers_url)` with a `referrer_count` (`COUNT`), since
`jobref.companies` has one un-deduplicated row per employee registration
(see below) and a seeker shouldn't see "Acme Corp" listed three times just
because three employees registered there. Sorted alphabetically by name.
Behind `get_current_user` like everything else in Jobref, but not
restricted to seekers specifically — it's non-sensitive directory data
(a company name + a careers URL an employee chose to share), and the
dashboard is what decides who sees it, not the API.

**Frontend**: `jobref/api/companies.ts` (thin `listCompanies()` wrapper),
`Dashboard.tsx` fetches it in a `useEffect` gated on `!isEmployee` and
renders a card per company (name, "Careers page ↗" link, a
`referrer_count` badge reusing the `--success` token to read as a
positive/available signal, distinct from the existing `--warn`-colored
role pill). Loading/error/empty states handled explicitly rather than a
blank gap. Employees see nothing new — the section doesn't render for
them at all.

**Verified locally** (real, not mocked): registered two employees at the
same company name to confirm the grouped count (`referrer_count: 2`)
alongside a third at a different company (`referrer_count: 1`); confirmed
`GET /companies` requires auth (`403` unauthenticated). Full real-browser
check via a small Playwright driver script (Vite dev server + tokens
seeded directly into `localStorage`, since driving the actual
login/LinkedIn forms wasn't needed to test this specific page): seeker
dashboard screenshot shows the "Companies available for referrals" heading
with a company card, correct careers link, and a "1 referrer" badge;
employee dashboard screenshot confirms the section is entirely absent.
Zero console errors on either. `tsc --noEmit` clean. Test data cleaned up
afterward on both frontend and DB.

**Deployed and re-verified in production**: no new migration needed (pure
API/frontend addition). Re-ran the grouping check directly against prod —
`GET /companies` correctly shows "Verify GmbH" with `referrer_count: 3`
(the 3 existing test employees there) alongside the other companies, each
counted correctly; unauthenticated request still `403`s. Cloudflare Pages
auto-rebuilt on push — confirmed by finding the new "Companies available
for referrals" string in the live built JS bundle at `www.lvamo.com`.
Applaut regression clean (health check).

## Companies-gathering step (Aug 2026, deployed)

User's request: during employee registration, capture the company name +
careers page URL the employee entered into a dedicated `jobref.companies`
table, linked back to the registering employee's UUID. Framed as seed data
for the future referral-matching feature — a job seeker will eventually
browse a companies list to find one with employees willing to refer,
rather than that living only inside individual employee rows.

**Design calls made** (the ask specified what to capture; the shape below
was improvised, per the go-ahead to do so):
- **Own table, own `id`** — `jobref.companies` has its own UUID primary
  key rather than reusing `user_id` as the PK (the pattern the old,
  pre-merge `jobref_employee_profiles` used). Company rows aren't
  guaranteed to stay 1:1 with employees forever — if a future dedup pass
  wants multiple employees pointing at the same company, or a company row
  gets referenced from elsewhere, having its own stable identity avoids a
  PK migration later.
- **One row per employee registration for now, `user_id` UNIQUE** — no
  deduplication by company name across different employees registering at
  the same company. Two employees at "Acme Corp" today get two separate
  `jobref.companies` rows. Left deliberately unresolved: deduping (by
  name? by careers URL? fuzzy-matched?) is a real design question that
  belongs with the referral-matching feature itself, not bolted on here
  ahead of that design.
- **Columns named `name`/`careers_url`, not `company_name`/
  `company_careers_url`** — dropped the `company_` prefix since it's
  redundant once the table itself is named `companies`
  (`companies.company_name` reads worse than `companies.name`).
- **`ON DELETE CASCADE`** from `jobref.users` — matches the cascade
  convention used everywhere else in this app; if an employee's account is
  deleted, their company entry goes with it.

**Migration `0014_jobref_companies.py`**: creates the table, then
backfills one row per existing employee (`WHERE is_employee`) so no
already-registered employee's company data is missing from the new table.

**Code changes**: new `models/jobref_company.py` (`JobrefCompany`).
`services/auth.py`'s `_register_employee` now flushes the `JobrefUser`
insert first (to get its generated `id`), then adds the `JobrefCompany`
row in the same transaction before committing — atomic: either both rows
land or neither does. Job-seeker registration is untouched (no company
data to capture there).

**Verified locally** (real, not mocked): migration applied, `\d
jobref.companies` confirms the exact shape (own PK, `user_id` UNIQUE FK,
CASCADE). Real employee registration → `201`, DB join confirms the
`jobref.companies` row landed correctly linked to the new employee's
`user_id`. Real job-seeker registration alongside it → confirmed it does
**not** create a companies row (row count stayed at 1 after both
registrations). Deleting the employee's user row cascaded correctly to
delete their companies row too — no orphans. Regression: Applaut/Jobref
health + login checks clean. Frontend: `tsc --noEmit` clean (no frontend
files touched — this is a pure backend/DB change, no API/UI surface added
yet).

**Deployed and re-verified in production**: migration `0014` ran clean on
the VM; backfill correctly populated one row per each of the 4
already-registered employees (confirmed via a DB join). A real
registration against prod → `201`, company row confirmed correctly linked,
then deleted — cascaded to remove the company row too, no orphans.
Applaut/Jobref health regression clean.

No API endpoint exposes `jobref.companies` yet (e.g. for a future "browse
companies" page) — intentionally out of scope until the referral-matching
feature gets designed and needs it.

## DB restructure: single `jobref.users` table (Aug 2026, verified locally)

User's explicit request: replace the 3-table split
(`jobref_users`/`jobref_employee_profiles`/`jobref_seeker_profiles`, all
unschemaed in `public`) with **one** table, `jobref.users` — living in the
`jobref` Postgres schema (created empty in migration `0012`, see
`PROGRESS_APPLAUT.md`; this is the deferred follow-up that closes that
out), with `is_employee` (boolean) as the sole differentiator and every
field only meaningful to one user type left `NULL` for the other.

**Decisions clarified before implementing** (flagged since several parts
of the original ask were non-standard vs. how the rest of the app is
built — user's own house rule is to call these out):
- **`NULL` for "not applicable" fields, not the literal string `"NA"`** —
  keeps `working_since` a real `DATE`, the four bucketed fields real
  constrained values, etc. Matches the existing `linkedin_id` column's
  convention (already nullable UNIQUE) rather than forcing every column to
  plain text.
- **A 5-digit auto-increment user ID was dropped entirely** — first
  proposed as a friendly extra column, but once discussed further the user
  concluded it's unnecessary since UUID is already the primary key. No
  integer ID column exists on the merged table.

**Migration `0013_jobref_merge_users_table.py`**: creates `jobref.users`
with all columns from the 3 old tables flattened in, `is_employee` in
place of the old `user_type` enum, 4 enum-membership CHECK constraints (as
before — Jobref's enums have always been plain `VARCHAR` + `CHECK`, not
native Postgres enum types, unlike Applaut's) plus 5 new CHECK constraints
enforcing the employee/seeker field-presence rules at the DB level
(defense in depth over the existing Pydantic conditional validation) —
required-when-employee, absent-when-seeker, required-when-seeker,
absent-when-employee, and the `notice_join_date`-iff-`serving_notice` rule.
Data is carried over via `INSERT ... SELECT` with a `LEFT JOIN` across the
3 old tables (not a destructive rebuild) before they're dropped.
`downgrade()` reverses it faithfully — recreates the 3 old tables in their
exact pre-migration shape (matching the cumulative result of migrations
`0007`–`0011`) and splits the data back out.

**Code changes**:
- `models/enums.py` (new) — `JobrefUserType`, `ReferFrequency`,
  `ReferralViewCapacity`, `JobSeekerStatus` all consolidated here (matches
  the `app/applaut/models/enums.py` convention already used on the Applaut
  side). `JobrefUserType` survives as a pure API-level type (still backs
  `RegisterRequest`'s discriminated union) even though it's no longer a DB
  column.
- `models/jobref_user.py` — single `JobrefUser` model, `__tablename__ =
  "users"`, `__table_args__ = {"schema": "jobref"}`. `models/
  jobref_employee_profile.py` and `models/jobref_seeker_profile.py`
  deleted (their model classes no longer exist; their enums moved to
  `enums.py`).
- `services/auth.py` — `_register_employee`/`_register_seeker` now build
  one `JobrefUser` row with every field set directly, instead of a user
  row plus a separate child-profile row across two inserts.
  `get_current_user` does a plain `db.get(JobrefUser, id)` — the old
  `_get_with_profiles` `selectinload` helper is gone, nothing to eager-load
  any more.
- `schemas/user.py` — **API response contract deliberately left
  unchanged** (still nested `employee_profile`/`seeker_profile` objects
  under `JobrefUserResponse`, still a `user_type` field) so **zero
  frontend changes were needed**. Added `JobrefUserResponse.from_user()`,
  which reshapes the flat ORM row back into that nested shape; the `/me`
  route now calls it explicitly rather than relying on Pydantic
  `from_attributes` against relationship attributes that no longer exist.
- `migrations/env.py` — updated the now-stale
  `JobrefEmployeeProfile`/`JobrefSeekerProfile` import.

**Verified locally** (real, not mocked): migration applied cleanly;
`\d jobref.users` confirms the exact intended shape (21 columns, all 9
CHECK constraints, both UNIQUE constraints); old 3 tables gone. Full API
round trip after a backend restart: employee register → `201`, `/login` →
`200`, `/me` → `200` with `employee_profile` correctly populated and
`seeker_profile: null`; missing a required employee field → `422`; job
seeker register via a minted registration token (same pattern used for
LinkedIn-flow testing when real credentials aren't being exercised) →
`201`, `/me` → `200` with `seeker_profile` populated (incl.
`notice_join_date`) and `employee_profile: null`. Direct DB check confirms
one row per user with the other type's fields genuinely `NULL` (not
`"NA"`). Regression: Applaut health/login and Jobref health/LinkedIn-
authorize-redirect all unaffected. Frontend: `tsc --noEmit` clean with
zero file changes on the frontend side, confirming the API contract really
didn't move.

**Deployed and re-verified in production**: migration `0013` ran clean on
the VM. The 3 disposable test rows that were in the old
`public.jobref_users` (`claude.verify.employee@example.com`, `prod.
fieldverify@example.com`, `prod.capacityverify@example.com` — all Claude's
own earlier verification accounts) carried over into `jobref.users`
correctly via the migration's `INSERT ... SELECT`, confirmed via direct DB
query. A real registration + cleanup against prod re-confirmed the write
path; Applaut/Jobref health and login regression checks clean.

## Referral capacity: always-asked, bucketed scale (Aug 2026, live in production)

Follow-up to the field added in the previous entry — user's explicit
request: drop the "I can refer other candidates at my company" checkbox,
ask the capacity question directly and unconditionally, and reuse the
*same* bucketed answer scale as the daily-view-cap field instead of a free
number.

- **UI**: "How many referrals can you do in a…" followed by a Week/Month
  segmented toggle (two buttons, not a dropdown — chosen for a binary
  choice, matches the app's existing card/button visual language), then a
  `<select>` with the same four options as `daily_referral_view_cap` (`Max
  5`/`5 - 10`/`10 - 20`/`No Cap`). Always visible now — no conditional
  reveal, no checkbox anywhere in the form.
- **Backend**: `can_refer` (boolean) and `refer_count` (integer) dropped
  entirely from `jobref_employee_profiles`. `refer_frequency` goes from
  optional/conditional to always `NOT NULL`. New `referral_capacity` column
  reuses the `ReferralViewCapacity` enum (same Python enum class as
  `daily_referral_view_cap`, given a distinct SQL constraint name —
  `jobref_referral_capacity` vs. `jobref_referral_view_capacity` — since two
  CHECK constraints on the same table need distinct names even when they
  share a value set). `EmployeeDetails`'s old conditional validator
  (`check_refer_fields`) is gone too — nothing conditional left to validate.
  Migration `0011`: drops the old `jobref_employee_refer_fields_chk`
  constraint first (since it referenced the columns being dropped),
  backfills the same handful of disposable test rows, enforces the new
  `NOT NULL`s.
- **Also updated**: `Dashboard.tsx` (which reads `employee_profile` fields)
  — was still referencing `can_refer`/`refer_count`, caught immediately by
  `tsc` failing the build. Now shows two rows: "Referrals" (bucketed
  capacity + frequency) and "Requests viewed" (daily view cap), via a small
  `CAPACITY_LABEL` lookup shared for both.

**Verified locally** (real, not mocked): backend — register with both new
fields → `201`; missing `referral_capacity` → `422`. Frontend — `tsc`/`vite
build` clean (only after fixing the `Dashboard.tsx` fallout above — a real
example of why a full build check catches more than just the page you're
looking at); Playwright confirms zero checkboxes in the form, both toggle
buttons present and functional (clicked "Month", it took), a full real
browser submission through choice→employee form→both new fields→submit
lands on `/jobref/dashboard`, which correctly displays the submitted values
("10 - 20 Per Month", "5 - 10 Per Day" in this run).

**Deployed and re-verified in production**: pushed, migration `0011` ran
clean on the VM, Cloudflare Pages auto-rebuilt. Re-ran the same checks
directly against production: real registration with both fields → `201`,
missing `referral_capacity` → `422`; `www.lvamo.com` confirmed showing
zero checkboxes and both working toggle buttons; Applaut regression clean.

## New employee field + disclaimer reword (Aug 2026, live in production)

Two small, unrelated changes requested together:

**1. New required employee field**: "How many referral requests can you
view per day?" — a dropdown (`Max 5` / `5 - 10` / `10 - 20` / `No Cap`)
placed immediately before the existing "I can refer other candidates"
checkbox section, per the user's specified placement. Deliberately modeled
as a *separate* dimension from `can_refer`/`refer_frequency`/`refer_count`
(which is about how many candidates they'll actively refer) — this is about
capacity to review *incoming* requests, so it's always required, not gated
behind the `can_refer` checkbox.

- Backend: new `ReferralViewCapacity` str-enum
  (`up_to_5`/`5_to_10`/`10_to_20`/`no_cap`) in
  `models/jobref_employee_profile.py`, new `daily_referral_view_cap` column
  (`NOT NULL`, CHECK constraint), migration `0010`. `EmployeeDetails`
  schema and `EmployeeProfileResponse` both updated; `_register_employee`
  persists it.
  - **Existing-row backfill note**: only disposable test data exists in
    `jobref_employee_profiles` at this point (Jobref just launched, no real
    employees registered yet) — the migration backfills those rows to
    `'no_cap'` before enforcing `NOT NULL`, since every *new* registration
    now always supplies a real answer via the required form field. Worth
    knowing if this migration is ever read later and the backfill value
    looks arbitrary — it is, deliberately, because no real user's answer
    existed to preserve.
- Frontend: `EmployeeDetails`/`ReferralViewCapacity` types in `api/auth.ts`,
  new `<select>` in `Register.tsx`'s employee form at the exact position
  requested, defaults to `up_to_5`.

**2. Disclaimer reworded** (Job Seeker panel) — user's specific concern:
the old copy ("...so you don't end up with more than one account")
indirectly framed *the user* as the one who might create duplicates. New
copy states the platform's general policy instead, no "you" framing: "We
use LinkedIn to sign you in. We only take your name and email address from
your LinkedIn profile — nothing else. This is used to prevent duplicate
accounts on Jobref."

**Verified locally** (real, not mocked): backend — register with the new
field → `201`; register missing the field → `422` field-required error,
confirming it's genuinely enforced. Frontend — `tsc`/`vite build` clean;
Playwright confirms the new field's label is present and correctly
positioned, a full real browser submission through the choice→employee
form→new field→submit flow lands on `/jobref/dashboard`; the seeker panel
shows the new disclaimer text and confirms the old accusatory phrasing is
gone.

**Deployed and re-verified in production**: pushed, `deploy.sh` ran
migration `0010` clean on the VM, Cloudflare Pages auto-rebuilt. Re-ran the
same checks directly against production: real registration with the field
→ `201`, missing it → `422`; `www.lvamo.com` frontend confirmed showing the
new field (correct position) and the new disclaimer text (old phrasing
gone); Applaut regression clean. Zero console errors throughout.

## Progressive disclosure: choice screen first, then the relevant path only (Aug 2026, live in production)

Same-day UX refinement on top of the split-registration work below — user's
request, reasoning given directly: the always-visible two-column layout
(full employee form + LinkedIn card side by side) "looks okay" on desktop
but crowds mobile with a full form and a competing option both visible at
once. Changed `/jobref/register` to a three-state flow instead:

1. **Choice screen** (default, no query param) — just "I am a" + two large
   tappable cards (Full-time Employee / Job Seeker), zero form fields, zero
   LinkedIn button. Nothing to scroll past on mobile.
2. **`?as=employee`** — the full direct-registration form (unchanged
   fields/logic from the split-registration work), plus a "← Back" link.
3. **`?as=job_seeker`** — the disclaimer + "Continue with LinkedIn" button
   (unchanged), plus "← Back".

**Why a URL param instead of just `useState`**: so the browser's native
back button works correctly (returns to the choice screen, not off the
page or to a stale form) and a direct link/refresh to `?as=employee` lands
correctly too — both verified via Playwright (`page.goBack()` after
picking a path correctly landed back on the zero-input choice screen).

Backend untouched — this is purely `frontend/src/jobref/pages/Register.tsx`
restructured around the same `EmployeeRegisterPayload`/LinkedIn-authorize
logic as before; `RegisterComplete.tsx` (the post-LinkedIn seeker form) is
unaffected.

**Verified locally**: `tsc --noEmit` + `vite build` clean. Playwright across
desktop + mobile viewports: choice screen has zero `<input>`/LinkedIn-button
elements; clicking each card updates the URL and reveals only that path's
content; "Back" link and the browser's actual back button both correctly
return to the zero-input choice screen; zero console errors throughout. Full
real browser submission of the employee form through the new flow (choice →
fill → submit) → landed on `/jobref/dashboard` cleanly, same as before this
change.

**Deployed and re-verified in production** (pure frontend change, no
migration needed): pushed, Cloudflare Pages auto-rebuilt, live within
moments — re-ran the same checks against `https://www.lvamo.com/jobref/register`
itself: zero-input choice screen, employee card reveals the form with the
correct `?as=employee` URL, and the browser's actual back button correctly
returns to the zero-input choice screen. Zero console errors.

## Split registration: employees direct, job seekers via LinkedIn (Aug 2026, live in production)

Same-day follow-up to the LinkedIn-gated registration work above — user's
explicit request: **employees should not have to go through LinkedIn at
all.** Registration is now split into two independent paths sharing one
page:

- **`/jobref/register`** is now two side-by-side cards under a shared
  "I am a" heading (stacks vertically on mobile via plain flexbox
  `flexWrap` reflow — this codebase's existing responsive convention, no
  CSS breakpoints needed): **Full-time Employee** (left) has the complete
  registration form inline — name, email, phone, password, domain, company
  fields — and submits directly, no LinkedIn involved at all. **Job
  Seeker** (right) is unchanged from before: a short disclaimer + "Continue
  with LinkedIn", flowing into `/jobref/register/complete` exactly as
  before.
- **Disclaimer copy updated** (user's request) — dropped the "we don't see
  your connections, we never post on your behalf" language; now just:
  "We only take your name and email address from your LinkedIn profile —
  nothing else — just so you don't end up with more than one account."
  Shorter, states the *reason* (dedup) rather than a list of things it
  isn't.
- **`/jobref/register/complete`** (the post-LinkedIn form) simplified —
  dropped the "I am a" employee/seeker toggle and all employee-specific
  fields, since this page is now only ever reached via the job-seeker
  LinkedIn path. Seeker fields only.

### Backend: discriminated union replaces the single conditional schema

`RegisterRequest` was a single Pydantic model with optional
`employee`/`seeker` fields and a manual validator enforcing "the one
matching `user_type` must be set." Replaced with two separate models
(`EmployeeRegisterRequest`, `SeekerRegisterRequest`) combined into a
`Annotated[Union[...], Field(discriminator="user_type")]` — FastAPI/Pydantic
route the request body to the correct model automatically, so each shape
only carries the fields it actually needs (no `Optional[EmployeeDetails] =
None` sitting on a seeker payload, no "must supply email OR
registration_token depending on type" ambiguity). `services/auth.py`'s
`register()` is now a thin dispatch (`isinstance` check) to
`_register_employee` / `_register_seeker`, each with its own dedup logic:

- **Employee**: dedup by email only (same as pre-LinkedIn registration
  ever was) — `linkedin_id` is `NULL`.
- **Seeker**: unchanged — dedup by `linkedin_id` (primary) or email
  (defense in depth), identity sourced from the verified
  `registration_token`, exactly as before.

**DB change**: `jobref_users.linkedin_id` was `NOT NULL UNIQUE` — now just
`UNIQUE` (nullable), migration `0009`. Postgres allows multiple `NULL`s
under a `UNIQUE` constraint, so this doesn't weaken the seeker-side dedup
at all; it just lets employees have no LinkedIn identity.

### Verified locally (real, not mocked)

- Backend: both paths exercised directly against the real local DB —
  employee register → `201`, duplicate email → `409 "Email already
  registered"`; seeker register (via a minted registration token, same
  pattern as the earlier mocked test) → `201`; malformed employee payload
  (missing `employee` key) → `422` with a clear field-location error.
  Confirmed in DB: employee row has `linkedin_id = NULL`, seeker row has
  the real value.
- Frontend: `tsc --noEmit` + `vite build` clean. Playwright: desktop
  screenshot shows the two-column split exactly as specified (single email
  input — employee's — confirming no LinkedIn-path fields leaked into the
  employee card); mobile screenshot confirms clean vertical stacking.
  **Full real browser submission** of the employee form (fill every field,
  click "Create account") → landed on `/jobref/dashboard`, zero console
  errors — this is a real gap closed from the previous entry, where nobody
  had completed an actual submission end-to-end through the UI.

### Not yet done

- ✅ Pushed and deployed — see banner at top of this file for the production
  verification log.
- The job-seeker path's *actual account-creation step* (as opposed to just
  the OAuth handshake) still hasn't been exercised through a real LinkedIn
  consent screen + real form submission — only via a minted token. Still
  the one open gap — see banner at top of this file.

### Mobile-first follow-up: app-wide input sizing fix (same session)

User asked directly whether this work was mobile-first — honest answer was
"the layout reflows correctly, but two real gaps exist in the shared global
CSS that this input-dense form inherits and would expose most": input
`font-size` was `0.875rem` (14px, computed — root `html` has no explicit
`font-size` so `rem` resolves against the 16px browser default, not the
body's 15px), below the 16px threshold that prevents iOS Safari's
auto-zoom-on-focus; and touch-target height (~34-39px) sat under the 44px
Apple HIG / WCAG 2.5.5 comfort guideline (still cleared WCAG 2.2 AA's 24px
hard minimum, so not a strict compliance failure, just below best practice).
Playwright/Chromium doesn't reproduce the iOS zoom behavior, so this wasn't
caught by any of the earlier screenshot-based checks — only surfaced by
actually computing `font-size` in px via `getComputedStyle`.

**Fixed app-wide** in `frontend/src/index.css`'s shared `input, select,
textarea` rule (affects every form in both verticals, not just this page):
`font-size: 0.875rem` → `1rem` (16px), `padding: 0.5rem 0.75rem` → `0.75rem`
(pushes intrinsic height to 46px, clearing the 44px guideline). Verified via
`getComputedStyle` at a 390px mobile viewport across Jobref register/login
*and* Applaut login (regression) — all report `font-size: 16px`; register's
email input measures 46px tall. Full visual regression (`tsc`, `vite
build`, Playwright screenshots at desktop + mobile across 4 pages) — zero
console errors, no visual breakage. Re-ran the real employee-form browser
submission end-to-end after the change — still lands on `/jobref/dashboard`
cleanly with the larger inputs.

Jobref is LVAMO's second vertical — a job-referral platform connecting job
seekers with employees willing to refer them at their company. As of Aug
2026, auth (register/login/me) is fully built end-to-end (backend + DB +
frontend) and verified locally; nothing beyond auth exists yet (no referral
matching, no messaging, no notifications).

## What exists today

- **Backend** (`backend/app/jobref/`), mounted at `/api/v1/jobref/*`:
  - `models/`: `jobref_users` (shared fields incl. `domain` — free-text
    professional field/industry, same concept for both employee and job
    seeker per the resolved open question), `jobref_employee_profiles`,
    `jobref_seeker_profiles` (both 1:1 on `user_id`, `ON DELETE CASCADE`).
  - `schemas/auth.py`: `RegisterRequest` with conditional `employee` /
    `seeker` sub-payloads gated by `user_type`; Pydantic validators enforce
    the conditional-required fields (`refer_frequency`/`refer_count` only
    when `can_refer=true`; `notice_join_date` only when
    `current_job_status=serving_notice`) and a loose German phone number
    format check.
  - `services/auth.py`: register/login/`get_current_user`, reusing shared
    `app/core/security.py` (hash/verify password) and `app/db/session.py`.
  - **Vertical-scoped JWTs**: `core/security.py`'s `create_access_token` now
    accepts optional `extra_claims`; Jobref stamps `{"vertical": "jobref"}`
    on every token it issues, and its `get_current_user` rejects any token
    missing that claim — so a token minted for Applaut (or a future
    vertical) can never be replayed against Jobref's endpoints, even though
    JWT signing secret/algorithm are shared infra. Applaut's own tokens are
    unchanged (no claim added, same as before).
  - Router: `api/v1/routers/{health,auth}.py` → `/register`, `/login`,
    `/me`. Registration is **open** (no invite gate, unlike Applaut).
  - Migration `0007_jobref_tables.py` — raw-SQL, matches repo convention
    (see `0006_application_settings.py`), incl. DB-level CHECK constraints
    mirroring the Pydantic conditional-field rules as defense in depth.
- **Frontend** (`frontend/src/jobref/`), routes under `/jobref/*`:
  - `api/client.ts` — own axios instance, own token key
    (`jobref_access_token`, never collides with Applaut's
    `applaut_access_token`).
  - `context/AuthContext.tsx` (`JobrefAuthProvider` / `useJobrefAuth`),
    `components/ProtectedRoute.tsx` (`JobrefProtectedRoute`) — independent
    of Applaut's equivalents, same shape.
  - `pages/Jobref.tsx` — updated from the old "coming soon" placeholder to
    a real landing page with "Get started" / "Sign in" CTAs.
  - `pages/Login.tsx`, `pages/Register.tsx` (full conditional form: shared
    fields, employee/job-seeker type selector, conditional sub-fields),
    `pages/Dashboard.tsx` (minimal post-auth profile summary + sign out).
  - Wired into `App.tsx`: `JobrefAuthProvider` wraps the router alongside
    Applaut's `AuthProvider` (siblings, fully independent state).
- **Verified locally**: backend boots clean, migration applied, full
  register→login→`/me` flow tested via curl for both user types plus
  validation edge cases (bad German phone, missing conditional fields,
  cross-vertical token rejection). Frontend: `tsc --noEmit` and
  `npm run build` clean; full Playwright pass through
  hub→landing→register (both types)→dashboard→logout→login→dashboard, plus
  an Applaut-page regression check — zero console errors.

## LinkedIn OAuth registration (Aug 2026, live in production)

Registration is now gated through LinkedIn OAuth (user's explicit request):
LinkedIn is the **only** option shown on the register page, used purely as
an identity/prefill source — **login stays email/password, unchanged.** The
account itself is only created once the user completes the existing
registration form (password + all employee/seeker fields); LinkedIn just
supplies verified name + email and prevents duplicate accounts.

**Flow** (server-driven redirects — the Client Secret never reaches the
frontend):
1. `/jobref/register` shows only a disclaimer (exactly what's requested:
   name + email, nothing else — no connections, no posting) + "Continue with
   LinkedIn", which is a plain link to `GET
   /api/v1/jobref/auth/linkedin/authorize` (a redirect, not an XHR call).
2. Backend builds LinkedIn's authorize URL with a signed, short-lived (5 min)
   `state` JWT for CSRF — stateless, no server-side session needed — and
   302s to LinkedIn.
3. LinkedIn redirects to the backend's registered callback, `GET
   /api/v1/jobref/auth/linkedin/callback`. Backend exchanges the code
   server-side (`app/jobref/services/linkedin.py`), calls LinkedIn's OIDC
   `userinfo` endpoint for `given_name`/`family_name`/`email`.
4. **Dedup on LinkedIn's stable member id (`sub`), not email** — checked
   against `jobref_users.linkedin_id` (new column, migration `0008`, `UNIQUE
   NOT NULL`) OR email match, both as defense in depth:
   - Already registered → redirect to `/jobref/login?linkedin=existing`
     (banner shown, login form unchanged below it).
   - New → mint a short-lived (15 min) signed `registration_token` carrying
     the verified LinkedIn id/email/name → redirect to
     `/jobref/register/complete?token=...`.
5. `RegisterComplete.tsx` fetches `GET /auth/linkedin/prefill?token=` to show
   exactly what was pulled from LinkedIn (transparency, per the user's
   request), pre-fills name (editable) + email (locked, badged "via
   LinkedIn ✓"), then the same password + domain + user_type + conditional
   employee/seeker fields as before. Submits to `POST /auth/register` with
   `registration_token` instead of a raw email — **the account's email and
   `linkedin_id` are always sourced server-side from the verified token,
   never trusted from client input** — a DB-level unique constraint on
   `linkedin_id` backstops the dedup against races (caught as 409).

**What changed, file by file:**
- Backend: `config.py` (+3 LinkedIn settings, +`frontend_base_url`),
  `core/security.py`'s `create_access_token` gained an optional
  `expires_minutes` override (generic, used for the short-lived state/
  registration tokens), `models/jobref_user.py` (+`linkedin_id` column),
  migration `0008_jobref_linkedin.py`, `schemas/auth.py`
  (`RegisterRequest.email` → `registration_token`; added
  `LinkedInPrefillResponse`), new `services/linkedin.py`, new
  `api/v1/routers/linkedin.py` (mounted in `router.py`),
  `services/auth.py`'s `register()` rewritten to decode the token and
  dedup on `linkedin_id`.
- Frontend: `api/auth.ts` (`RegisterPayload.email` → `registration_token`,
  +`linkedInAuthorizeUrl()`, +`getLinkedInPrefill()`), `pages/Register.tsx`
  rewritten as the disclaimer + LinkedIn-only CTA, new
  `pages/RegisterComplete.tsx` (the old form, minus a free-text email
  field), `pages/Login.tsx` (+banner for `?linkedin=existing`), new route
  `jobref/register/complete` in `App.tsx`.

**Verified this session** (backend has no real LinkedIn credentials yet, so
verified as far as possible without them):
- Backend: full callback→register flow exercised in-process against the
  real local DB with LinkedIn's token-exchange/userinfo calls mocked —
  registration succeeds, a second callback with the same LinkedIn `sub` is
  correctly caught as `existing_account`. `alembic upgrade head` (0008)
  clean. Truncated 6 leftover local test rows from last session (throwaway
  `@example.com` accounts, nothing real) since the new `linkedin_id` column
  is `NOT NULL` — noted here in case anyone wonders why the local dev table
  is suddenly empty.
- Frontend: `tsc --noEmit` + `vite build` clean. Full Playwright pass:
  `/jobref/register` shows zero email/password inputs, only the disclaimer +
  correctly-pointed LinkedIn link; `/jobref/register/complete` with no token
  shows the "start over" error state; `/jobref/login?linkedin=existing`
  shows the banner above an otherwise-untouched login form;
  `/jobref/register/complete?token=<real backend-issued token>` renders
  fully prefilled (name editable, email locked+badged) — all with zero
  console errors.

**Update — real LinkedIn credentials arrived, tested for real (Aug 2026):**
user created the LinkedIn app, credentials added to local `.env`. Full real
browser round-trip through the actual LinkedIn consent screen worked
cleanly, confirmed via backend logs: `authorize` → 307 to LinkedIn →
`callback?code=...` → 307 to `/jobref/register/complete?token=...` →
`prefill` → 200 OK with real decoded data (real email, real name). No mocks
involved. **However, the user stopped there and asked to deploy before
submitting the completed form** — so the actual `register()` call (password
hash, employee/seeker fields, `linkedin_id` insert) is still only verified
by Claude's earlier synthetic/mocked test, never by a real submission. See
"Production deploy" below and the banner at the top of this file.

---

## Production deploy (Aug 2026)

Pushed and deployed end-to-end, same session as the real LinkedIn OAuth
test above. Sequence:

1. `.env.production` on the VM was missing the LinkedIn/frontend-URL vars
   entirely (checked via `grep -oE '^[A-Z_]+='` — names only, values never
   printed; a plain `cat` of the file was correctly blocked by the
   permission classifier since it's a secrets file). Appended
   `JOBREF_LINKEDIN_CLIENT_ID`, `JOBREF_LINKEDIN_CLIENT_SECRET`,
   `JOBREF_LINKEDIN_REDIRECT_URI=https://api.jobref.lvamo.com/api/v1/jobref/auth/linkedin/callback`,
   `FRONTEND_BASE_URL=https://www.lvamo.com` directly via SSH heredoc, never
   round-tripped through a local file. Confirmed `BACKEND_CORS_ORIGINS`
   already included `https://www.lvamo.com` — no change needed there.
2. `git push origin main` — 6 commits (LinkedIn gating, dedicated hostname,
   var rename, this doc's updates).
3. `bash deploy.sh` on the VM — hit one snag: the VM's working copy of
   `nginx/nginx.conf` had an uncommitted local diff (from the earlier direct
   `scp` when setting up the dedicated hostname, done outside git on
   purpose at the time) that blocked `git pull`. Diffed it against
   `origin/main`'s version first to confirm byte-identical content, then
   `git checkout -- nginx/nginx.conf` to discard the redundant local copy
   and let the pull proceed. `deploy.sh` then ran clean: pulled, rebuilt the
   backend image, ran `alembic upgrade head` (`0006`→`0007`→`0008`),
   recreated the backend container, pruned old images. `nginx`/`postgres`
   untouched (no config changes to those this deploy).
4. **Verified in production** (all real, no mocks):
   - `GET https://api.jobref.lvamo.com/api/v1/jobref/health` → `200 OK`.
   - LinkedIn `authorize` redirect on the prod hostname carries the real
     `client_id` and the correct prod `redirect_uri`
     (`https://api.jobref.lvamo.com/...`, not the localhost one).
   - Regression: `api.applaut.lvamo.com` health + a real login attempt
     (401 on bad credentials, not a crash) — unaffected by any of this.
   - Playwright against the live production frontend: `/jobref/register`
     shows the LinkedIn-only page with the button correctly pointed at
     `api.jobref.lvamo.com` (proves the Cloudflare Pages env-var rename from
     earlier took effect on this build); `/applaut/login`'s failed-login
     error message rendered (proves it's hitting the real prod API under
     `VITE_APPLAUT_API_BASE_URL`, not falling back to `localhost:8000`) —
     zero console errors beyond the deliberately-triggered 401.
5. **Not verified in production**: an actual completed registration (see
   the callout above and the banner at the top of this file) — the user
   asked to deploy before finishing that local test, so the very first real
   account creation, whenever it happens, is also the first real test of
   that code path.

## Dedicated hostname: `api.jobref.lvamo.com` (Aug 2026, live)

Jobref's production backend now has its own hostname instead of sitting
under Applaut's (`api.applaut.lvamo.com` predates Jobref as a concept — see
`PROGRESS.md`'s Multi-Vertical Architecture section for the durable policy).
Live and verified today; only the DNS/TLS/nginx layer — no vertical code was
deployed as part of this.

**What was done:**
1. DNS: `A api.jobref.lvamo.com → 130.61.106.172`, DNS-only (grey-cloud,
   matching `api.applaut.lvamo.com`'s pattern), via the Cloudflare API.
2. TLS cert: `certbot certonly --webroot -w /var/www/certbot -d
   api.jobref.lvamo.com` on the VM — issued with **zero nginx downtime**,
   unlike the original `api.applaut.lvamo.com` cert which was issued via
   `--standalone` (had to, at the time — nginx didn't exist yet, chicken-
   and-egg problem, see "Oracle Backend Migration" in `PROGRESS.md`).
   Expires 2026-11-16, auto-renews via the existing `certbot.timer`.
   - **⚠️ Latent issue noticed, not fixed**: `api.applaut.lvamo.com`'s
     renewal config still says `authenticator = standalone`, which needs
     port 80 free — but the nginx Docker container now permanently holds
     port 80 (`restart: always`), with no pre/post renewal hook to stop it.
     Auto-renewal for that cert will likely **fail** when it's actually due
     (~mid-Oct 2026, 30 days before the Nov 15 expiry). Not urgent today,
     but worth fixing before then — either switch that cert to `--webroot`
     like Jobref's (re-issue once, same webroot path already exists in
     nginx.conf), or add a stop/start-nginx renewal hook.
3. `nginx/nginx.conf`: added a second `server { listen 443 ssl; server_name
   api.jobref.lvamo.com; ... }` block, proxying to the same `backend:8000`
   as the Applaut block — same shared backend process, just a second front
   door. Deployed to the VM directly (`scp` + `nginx -s reload`, no
   container restart, no downtime) since this is pure infra config, not the
   gated Jobref feature deploy — also committed to git locally.
4. Frontend: `jobref/api/client.ts` and `jobref/api/auth.ts` now read
   `VITE_JOBREF_API_BASE_URL` (own env var) instead of sharing Applaut's
   base URL var — both fall back to `http://localhost:8000` in dev (single
   shared backend container locally, so no behavior change there; verified
   via a real dev-server + Playwright check that the LinkedIn button's href
   is unchanged locally).
5. **Applaut's own var renamed too, for consistency**: `VITE_API_BASE_URL` →
   `VITE_APPLAUT_API_BASE_URL` (user's request, once two verticals existed
   side by side, `VITE_API_BASE_URL` was ambiguous about which backend it
   pointed at). Updated in `applaut/api/client.ts`, `.env`/`.env.example`,
   `README.md`.
   **⚠️ This one is already live in production** (unlike
   `VITE_JOBREF_API_BASE_URL`, which is net-new) — the Cloudflare Pages
   build var must be renamed too, in the same dashboard step as adding the
   Jobref one below, or the next Applaut frontend redeploy will silently
   fall back to `localhost:8000` and break the production API base URL.

**Verified:** new hostname serves the correct cert (`CN=api.jobref.lvamo.com`)
and correctly proxies to the shared backend (tested via the existing Applaut
health endpoint, since Jobref's own routes aren't deployed yet — got a clean
200). Old hostname re-tested afterward, unaffected. `tsc`/`vite build` clean
after the frontend env-var split.

**All of the below are now done** — see "Production deploy" above for the
full log:
- ✅ Cloudflare Pages build env vars renamed/added by the user, confirmed
  live on the current build (Playwright-verified against
  `www.lvamo.com` post-deploy).
- ✅ Production redirect URI registered on the LinkedIn app and confirmed
  working (real consent-screen round trip, see "LinkedIn OAuth
  registration" above).
- ✅ `.env.production` on the VM has the LinkedIn credentials +
  `FRONTEND_BASE_URL`.

## Resolved decisions (previously open)

- **`domain` field**: same free-text professional-field/industry concept
  for both employee and job-seeker registration — confirmed.
- **Registration gate**: open, no invite-gate.
- **CV Google-Drive-link**: required for job seekers.
- **`company_careers_url`**: made required for employees (core to the
  referral value prop — without it there's no way to point a job seeker at
  open roles).

## Next steps

- **How does a seeker find out their request was accepted/rejected?** No
  notification mechanism exists yet in either vertical (email, in-app, or
  otherwise) — the natural next feature now that there's a real decision
  to notify about. See "Employee actions on a referral request" above.
- ~~Evidence files aren't viewable~~ — built and pushed (`5bb67a7`, Aug
  2026): `GET /referral-requests/{id}/evidence` returns a 5-min presigned
  R2 URL to either party on the request; "See referral evidence" link on
  the seeker dashboard and employee detail page. **Live in production** —
  confirmed Oct 2026: prod backend container was built 2 min after the
  commit and contains `get_evidence_url`; unauthenticated hit on the
  route returns 403 (route exists), not 404.
- Cert auto-renewal (Oct 2026): `api.applaut.lvamo.com` still used the
  `standalone` authenticator (fails — nginx holds port 80), and **neither**
  cert had a deploy hook to reload nginx after renewal (so even Jobref's
  successful webroot renewal would keep serving the old cert until a
  container restart). **Fixed and applied in production 2026-10-11** via
  `nginx/setup-cert-renewal.sh` + `nginx/certbot-deploy-hook.sh`: Applaut
  cert re-issued with webroot (now expires 2027-01-09, confirmed served
  live via `openssl s_client`), reload hook installed, `certbot renew
  --dry-run` succeeded for both certs. See PROGRESS.md Deployment.

---

### Session update — auth built, deploy held (committed `3d5fd42`, local only)

Session end state, Aug 2026: full login/registration feature built and
verified locally (see "What exists today" above for the complete
breakdown). Committed to local `main` but the user chose not to push/deploy
today — everything above this line describes code that exists on disk and
in the local git history, not (yet) in production.
