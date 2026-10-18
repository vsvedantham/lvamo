# Connect your Claude routine to Applaut (engine 3)

For a routine that writes to Neon + Cloudflare R2 like
`vsvedantham/job-search-automation`. About 20 minutes. Applaut only ever
**reads** your data, with a role and a key you create for it. It never sees
your routine's own (read & write) credentials.

You need: an Applaut account with a profile, and access to your Neon project
and Cloudflare account.

---

## 1. Applaut account and profile (5 min)

1. Register at <https://www.lvamo.com/applaut/register> (only while
   registration is open).
2. Complete onboarding (roles, countries, skills). The job engine belongs to
   the profile, so this comes first.

## 2. A read-only Neon role for Applaut (5 min)

1. <https://console.neon.tech> → the project your routine writes to →
   **SQL Editor** (database `neondb`, or whichever database your routine's
   `JOBSEARCH_DB_URL` names).
2. Make a password: `openssl rand -hex 24` in Terminal (hex, so it needs no
   escaping in a URL; Neon rejects weak passwords).
3. Run, with your password:

   ```sql
   CREATE ROLE applaut_reader WITH LOGIN PASSWORD '<your hex password>';
   GRANT CONNECT ON DATABASE neondb TO applaut_reader;
   GRANT USAGE ON SCHEMA public TO applaut_reader;
   GRANT SELECT ON jobsearchautomationresults, run_tracker TO applaut_reader;
   -- tables the routine creates later are readable too
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO applaut_reader;
   ```

4. Get its connection string: project dashboard → **Connect** → role
   `applaut_reader` → copy. It looks like
   `postgresql://applaut_reader:<password>@ep-….neon.tech/neondb?sslmode=require`.
   Pooled or direct host both work.

## 3. A read-only R2 key for Applaut (5 min)

1. <https://dash.cloudflare.com> → **R2 Object Storage** → **Manage API
   tokens** → **Create API token**.
2. Permissions **Object Read only**; **Apply to specific buckets only** →
   `job-search-automation-documents`; TTL forever → **Create**.
3. Copy the **Access Key ID** and **Secret Access Key** (shown once). Your
   **Account ID** is on the R2 overview page (32 characters).

Recommended while you're there: replace your routine's own read & write key
(it was printed in a chat on 2026-10-17). Create a new **Object Read &
Write** token for the same bucket, put its id and secret into the routine's
environment in Claude **and** `~/.job-search-automation.env` (your Mac sync
uses it), then delete the old token. Do it between runs (they start 06:07
and 18:07 UTC).

## 4. Connect in Applaut (5 min)

1. **Settings** → **Job engine** → **Your Claude routine**.
2. Fill in:

   | Field | Value |
   |---|---|
   | Neon connection string | the `applaut_reader` string from step 2 |
   | Cloudflare account id | from step 3 |
   | R2 bucket | `job-search-automation-documents` |
   | Folder in the bucket | `jobautomationdocs` |
   | R2 access key id / secret | the read-only key from step 3 |
   | Routine link | your routine's page in Claude (address bar) |
   | Run times / Days / Timezone | `06:07, 18:07` · Every day · `UTC` |

3. **Test connection**: all six checks should be green. Applaut tries to
   write one empty file to prove the R2 key can't write; a read & write key
   is refused, and so is a Neon role that can change data.
4. **Save and connect**. The first sync starts within about two minutes.
5. **Documents on this computer**: leave `~/JobSearchDocuments` unless your
   Mac sync copies somewhere else.

## 5. Check it worked

- **Opportunities** → "From your Claude routine": your jobs, with match %,
  matched/missing skills and CHECK flags.
- **Settings** → **Syncs**: the first sync's counts; **Run history**: runs
  from `run_tracker`.
- **Dashboard**: the routine card shows the last run, last sync, next run.
- After each scheduled run Applaut checks at +30 min, +1 h, +2 h, +3 h and
  syncs an hour after the run finished. **Sync now** works once every 10 minutes.

To disconnect: Settings → **Remove connection** (stored keys are deleted at
once; synced jobs and documents stay). Then delete `applaut_reader` and the
read-only token.
