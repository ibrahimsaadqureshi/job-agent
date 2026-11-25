# Job Agent v2: Plan

A free daily pipeline that finds remote software jobs open to candidates in Pakistan,
scores them against my resume with a free LLM, drafts short application notes, logs
everything to a Google Sheet and sends one digest a day. I review and apply myself.

Status: **draft, waiting for approval.** No code is written until this is approved.

Decided with you (2026-11-25): digest goes to **Slack**, score threshold **70**, **Senior**
roles are kept and left to the LLM, and **automation gigs** appear in the digest and the Sheet.

---

## 0. What exists today and what to do with it

### What the repo has (about 2,300 lines of Python)

| Area | Files | State | Keep? |
|---|---|---|---|
| Entry point | `main.py` | Top-level script: fetch, then `INSERT OR IGNORE` into SQLite. No CLI, no config. | No |
| Sources | `scrapers/remoteok.py` | Works. But: no timeout, spoofs a `Mozilla/5.0` UA, ignores `location`, salary and date, and doesn't credit RemoteOK as its API terms require. | Idea only |
| | `scrapers/yc.py` | Scrapes `ycombinator.com/jobs` HTML and fetches every job page. Fragile, and scraping is out of scope for this project. | No |
| | `greenhouse/*` | Uses Greenhouse's public boards API (legitimate), but for 15 US-centric companies whose jobs are almost never open to Pakistan. | Later, maybe |
| Storage | `database/*` | SQLite file. Fine locally, but GitHub Actions has no persistent disk, so it can't be the source of truth there. | No |
| Filtering/ranking | `utils.py`, `config/keywords.py`, `ranking/*` | Keyword lists tuned for automation and VA/ops roles (`"make"`, `"ai"`, `"support"`), with substring matching (`"ai"` matches "maintain"). No location logic at all. | No |
| LLM | `experiments/assessment_utils.py`, `prompts/v3` | Ollama + qwen2.5:7b, with JSON validation and repair. The v3 prompt's "no unsupported claims" rules are good. | Prompt rules only |
| Eval | `experiments/eval/*` | Drift, consistency and hallucination audits for the Ollama runs. Thoughtful, but it serves a different design. | No (stays in git history) |
| Reports | `reports/*` | Ad-hoc SQL print scripts. | No |
| Tests | none | No tests, no dry-run, no CI, no `.env.example`. | |

### A privacy problem to fix before the repo goes public

An old experiment branch committed a sample resume with personal contact details. `main`
never contained it, and the repo was private at the time. Before making the repo public:
1. Build v2 on a fresh branch cut from `main`, so the resume never enters its history.
2. Delete that experiment branch from the remote.
3. Optional: ask GitHub Support to purge cached views of the commit.

From v2 on, the resume and every personal detail stay out of git. The resume is loaded at
runtime from a gitignored path locally, and from a secret in CI.

### Recommendation: rewrite inside the same repo

Start over in this repo, on a new branch cut from `main`. Reasons:
- Almost nothing matches the new goal. Sources, filters, scoring and storage all need
  different behaviour: location eligibility, cross-run dedupe without a local database,
  a hosted LLM, a Sheet and a digest. Patching would cost more than rewriting the ~600
  lines that matter.
- The code is script-shaped (work happens at import time, no functions to test), so it
  can't be tested without restructuring it anyway.
- Keeping the repo keeps the history and the name, and the rewrite is a clear "v2" story
  in the README for employers.
- What carries over: the RemoteOK fetch, the HTML-to-text cleanup, and the v3 prompt's
  anti-hallucination rules, reshaped for scoring and drafting.

---

## 1. Architecture

### Options

| | (a) Python on GitHub Actions cron | (b) Self-hosted n8n on my Mac |
|---|---|---|
| Runs when Mac is off/asleep | **Yes** | No. Misses days whenever the Mac sleeps. |
| Cost | Free (unlimited minutes for public repos) | Free |
| Secrets | GitHub Actions encrypted secrets | n8n credential store, local |
| Tests / dry-run | Native (pytest, CLI flags) | Hard. Workflows are JSON and need manual testing. |
| Version control | Plain code, reviewable diffs | Exported JSON blobs, noisy diffs |
| Portfolio value | Shows Python, testing, CI, API integration | Shows n8n (already on my resume) |
| Speed to build | Medium | Fast for me |

**Recommendation: (a) GitHub Actions.** "Runs every day on its own" is the core
requirement, and only (a) meets it without a machine staying on. It also gives tests and
a public, readable codebase, which is half the point of the repo.

Two gotchas to design around:
- **Public Actions logs.** Anyone can read the logs of a public repo. The pipeline will
  never print resume text, drafts or the Sheet ID. Logs show counts only. Secrets are
  masked automatically, but we won't rely on that alone.
- **Cron auto-disable.** GitHub disables scheduled workflows in public repos after 60
  days without repo activity. A small monthly keepalive step re-enables the workflow
  through the API, with no dummy commits.

### Flow

```
GitHub Actions cron (daily 03:00 UTC = 08:00 PKT)  +  manual "Run workflow" button
        │
        ▼
 fetch ── RemoteOK, Remotive, We Work Remotely, Himalayas, HN Who is hiring
        │  normalize to one Job model (id, source, company, title, url, location,
        │  salary, posted_at, description, tags)
        ▼
 filter ── tech-role rules → category: stack | automation | tech-entry | (drop non-tech)
        │  location rule → worldwide | asia | emea | pakistan | (drop)
        │  seniority rule → drop staff/principal/director/manager titles
        ▼
 dedupe ── in-run (same job on 2 boards) + cross-run (already in the Sheet)
        ▼
 score ── LLM, batched: fit 0-100 + one-line reason   (only new, filtered jobs)
        ▼
 draft ── LLM, per job above threshold: 80-120 word tailored note
        ▼
 sheet ── append rows (never touches rows I've edited)
        ▼
 digest ── top N new jobs from today → Slack incoming webhook
```

### Code layout

```
jobagent/
  models.py          Job dataclass, stable id
  sources/           remoteok.py remotive.py wwr.py himalayas.py hn.py  (fetch + parse)
  filters.py         keyword, category, location, seniority rules
  dedupe.py          URL canonicalization + company/title fingerprint
  llm.py             Gemini client, fallback client, JSON validation
  prompts/           score.txt  draft.txt
  sheet.py           Google Sheets read (seen ids) + append
  digest.py          message formatting + Slack webhook send
  config.py          env vars + local config, all in one place
  cli.py             `python -m jobagent run [--dry-run] [--no-llm] [--limit N] [--sources ...]`
tests/
  fixtures/          trimmed real responses from each source
  test_parsers.py  test_filters.py  test_dedupe.py  test_digest.py  test_llm_parse.py
.github/workflows/daily.yml   tests.yml
```

Dependencies stay small: `requests`, `beautifulsoup4`, `gspread` + `google-auth`, `pypdf`
(local resume extraction), `pytest`. I'll call Gemini over plain HTTPS, with no SDK, so
model and provider swaps stay trivial.

---

## 2. Sources

I verified each one **live on 2026-11-25**: all returned HTTP 200 with parseable data.

| Source | Endpoint | Format | What I saw | Notes |
|---|---|---|---|---|
| RemoteOK | `https://remoteok.com/api` | JSON | 100 latest jobs. `location` is a free string: 64 "US Only", 7 "Worldwide", 3 "EMEA", 2 "Asia". Has `salary_min/max`. | **Terms:** must link back to the RemoteOK URL and name RemoteOK as the source. The Sheet keeps their URL plus a `source` column, and the digest says "via RemoteOK". |
| Remotive | `https://remotive.com/api/remote-jobs` (all categories; the category filter adds nothing at 15 jobs) | JSON | Only **15 jobs**, the full public feed. `candidate_required_location` is a clean string ("Worldwide", "USA", ...). | **Terms:** link back + credit, jobs delayed 24h, don't republish to job boards. Low volume, cheap to include. |
| We Work Remotely | `https://weworkremotely.com/remote-jobs.rss` (all) plus the `categories/remote-{full-stack,front-end,back-end}-programming-jobs.rss` and DevOps feeds | RSS | 209 full-stack items. `<region>` field: 131 "Anywhere in the World", 35 "USA Only", 18 "Asia Only". | Title is "Company: Role", so I'll split it. Best source by volume of eligible jobs. |
| Himalayas | `https://himalayas.app/jobs/api/search?q=…&country=Pakistan` and `…&worldwide=true`, run for a short query list (developer, engineer, junior, automation, QA, support engineer, react, python) | JSON | `country=Pakistan&q=react` → 115 jobs whose `locationRestrictions` include Pakistan or are empty. Has salary, seniority, timezone. | Server-side Pakistan eligibility, the most precise source. 20 per page. The main feed has moved to cursor pagination. Their robots.txt only disallows `?page=` HTML pages, and the API is public. |
| HN Who is hiring | Algolia `search_by_date?tags=story,author_whoishiring` → `items/{id}` | JSON | Nov 2026 thread `50338728`: 238 top-level comments. | Free text. Parse the first `Company \| Role \| Location \| …` line, then keep only comments that say REMOTE plus worldwide/anywhere/global/Asia/EMEA. Each comment is deduped by id across the month. |

Every request sends an honest User-Agent (`job-agent/2.0 (+repo URL)`), a timeout and one
retry. A failing source is logged and skipped. It never fails the whole run.

### Deferred, and why

- **Wellfound**: no public API, its terms forbid scraping, and it sits behind bot protection.
- **YC Work at a Startup**: needs a login, with no public API. The old `yc.py` scraped
  ycombinator.com HTML instead, which I'm dropping for the same reason.
- **Arc.dev**: no public jobs API, and its terms restrict automated access.
- **Later candidates worth a look** (legitimate public APIs, not verified yet): Jobicy's
  remote jobs API, which has geo filters, and Greenhouse/Lever/Ashby public board APIs for a
  hand-picked list of remote-first companies known to hire in Asia (the old `greenhouse/`
  idea, aimed better).

---

## 3. Filtering

All rules are plain, unit-tested functions. Words match on word boundaries, not substrings,
so the old `"ai"` matching "maintain" can't happen.

**Category (title + tags, then description).** The net is wide on purpose: any tech role I
could start in and learn on counts, not only my current stack.
- `stack`: roles on my current stack: typescript, javascript, react, next.js, node, nestjs,
  full-stack/fullstack, frontend/front-end, mongodb, mern.
- `automation`: n8n, zapier, make.com, gohighlevel, workflow automation, RevOps/CRM
  engineering, integrations, automation engineer, AI automation, low-code. Freelance and
  contract gigs are included.
- `tech-entry`: any other technical role that is entry-level or open to learning:
  - **Software roles in any language:** Python, Go, PHP, Java, Ruby, .NET, mobile (React
    Native, Flutter), and so on.
  - **Other technical roles:** QA/test engineer, technical/product support engineer,
    implementation/solutions/integration engineer, junior DevOps/cloud, IT support, data
    analyst, developer relations, technical writer, AI/LLM engineer, prompt/AI trainer.
  - **Signal words:** junior, entry level, graduate, trainee, intern, apprentice, associate,
    early career, "0-2 years", "will train", "no experience required".
  - Software roles in another stack with no seniority marker are kept too. The LLM judges
    how far the gap is.
- Dropped before any LLM call: non-technical roles (sales, account executive, marketing,
  recruiting/HR, finance, legal, customer service without a technical side, content
  writing, pure visual design), and research roles needing a PhD.
- Category is a label, not a gate: it decides which digest section a job lands in.

**What "fit" means to the scorer.** A strong score doesn't require an exact stack match. The
rubric weighs:
- **Can I get hired:** level and years asked vs. mine, and region eligibility.
- **Can I ramp fast:** how close the stack is (TypeScript to Python is closer than to
  embedded C), and whether the posting mentions mentorship or training.
- **Will I grow:** whether the role builds real engineering skills.

So a junior Python backend role at a team that mentors can outscore a senior React role
asking for 6 years. The one-line reason says which gap matters ("Go is new to you, but the
role is junior and mentored").

**Location eligibility (the `location rule` column records why a job passed):**
- Pass: worldwide, anywhere (in the world), global, Asia/APAC, EMEA, Middle East, South Asia,
  Pakistan, a Himalayas restriction list containing Pakistan, or a timezone range covering UTC+5.
- Drop: US/USA/Canada/UK/Europe/LATAM "only", single-country lists without Pakistan, named
  cities, and description phrases like "must be authorized to work in", "US citizens",
  "security clearance", "W-2", "must reside in", "US-based".
- Blank or unclear location → kept, labeled `unspecified`. The LLM is told to cut the score
  if the text hints at a region lock. (RemoteOK blanks are rare: 1 in 100 today.)

**Seniority:** titles with staff, principal, director, head of, VP or manager are always
dropped. **Senior** roles are kept and go to the scorer. The scoring prompt states my real
experience (about 5 months with the full-stack title, 2 years at the company), so a role
asking for 5+ years scores low on its own merits. Any years-of-experience requirement found
in the text is passed to the LLM as a hint.

**Dedupe:**
- Job id = hash of the canonical URL (tracking params stripped, lowercased host).
- In-run duplicates (same job on WWR and RemoteOK, say): fingerprint = normalized company +
  normalized title. The first source wins and the others go into a `also on` note.
- Cross-run: at start-up, read the `id` column from the Sheet. Every job that passed the
  keyword filter gets a row (even if it scored low), so it's never re-scored or re-sent.
  The Sheet is the single source of truth, so the Actions runner needs no database and no
  state commits.
- In dry-run, a local `~/.config/job-agent/state/seen.json` stands in for the Sheet.

---

## 4. Scoring and drafting with a free LLM

- **Primary: Google Gemini API, free tier** (an AI Studio key, with no billing account
  attached, so it can't charge). I'll use the cheapest current Flash-class model and confirm
  the exact model name and free quota with `models.list` on your key in M3, before relying on it.
- **Fallback: GitHub Models** (free and rate-limited, using the workflow's built-in
  `GITHUB_TOKEN` with `models: read`, so there's no extra key). This replaces Ollama in CI,
  because a 7B model on a 2-core runner is too slow. I couldn't confirm its catalog without
  that permission, so I'll verify it in M3. If it doesn't work, the fallback is simply "leave
  unscored jobs for tomorrow". **Ollama** stays as an optional local provider
  (`LLM_PROVIDER=ollama`) for runs on the Mac.
- **Token budget:**
  - Only jobs that pass the category, location and seniority filters and are new are scored.
    With the wider categories, I expect about 20-60 a day. Rough volume from today's feeds:
    - We Work Remotely: about 100 jobs a month across all categories, nearly all open
      worldwide.
    - RemoteOK: about 25 a day, about 12% of them eligible.
    - Himalayas: the largest source.
    - HN: a monthly burst of about 240 posts.
  - **First run** is a backfill of everything currently listed, possibly a few hundred jobs.
    It's capped with `--limit` and spread over the first 2-3 days, so it stays inside the
    free quota.
  - **Scoring is batched:** about 10 jobs per request, each trimmed to title + company +
    location + about 1,000 characters of description, plus a condensed ~350-token profile.
    That's about 2-6 requests a day.
  - **Drafts run one per job, only for scores at or above the threshold.** Each is an
    80-120 word note, capped at about 10 a day.
  - Total: about 20 requests and roughly 60-100k tokens a day, still small for a free tier.
- **Profile:** locally, `pypdf` extracts the resume from the path in
  `~/.config/job-agent/config.toml` (outside the repo). Contact lines (phone, email, LinkedIn) are stripped **before** anything
  goes to an LLM. In Actions, that same stripped text lives in the `CANDIDATE_PROFILE` secret.
  A helper script prints it so you can paste it into the secret, and it's never committed.
- **Privacy note:** Google may use free-tier Gemini inputs to improve its products. So the
  only things sent are the stripped profile (skills and experience, no contact details) and
  public job text.
- **Output contract:** JSON `{id, score, reason}`, validated (integer 0-100, reason ≤ 140
  chars, ids match the input). On a bad response: retry once, then fall back to the next
  provider, then leave the job unscored (score blank, retried next run). Draft rules come from
  the old v3 prompt: never claim a skill the profile doesn't name. Tone is direct, no clichés,
  with one concrete matching project.

---

## 5. Output

### Google Sheet tracker

One tab, `Jobs`, with columns:

`date | source | company | title | link | location rule | salary | score | reason | draft note | status | category | id`

(`category` is `stack`, `automation` or `tech-entry`.)

That's your 11 columns plus `category` and a hidden `id` for dedupe.
- `status` starts as `new`. The pipeline only **appends**: it never edits existing rows, so
  your changes to status (applied / skipped / interviewing) are safe.
- Auth uses a **Google Cloud service account** with the Sheets API enabled. It's free and
  needs no billing. You share the Sheet with the service account's email.
- I'll add conditional formatting on score and a filter view once, by hand or with a setup
  script.

### Daily digest: Slack incoming webhook

Telegram needs a VPN in Pakistan, so the digest goes to a **Slack incoming webhook** in a free
Slack workspace that only you are in:
- The Slack phone app gives a push notification.
- Sending is a single HTTPS POST, and the webhook URL is the only secret.
- Block Kit formatting gives clickable titles and clean sections.
- The free plan's 90-day message history doesn't matter, because the Sheet is the
  permanent record.

There is **one message per day**:
- Top new jobs scoring **70 or more**, grouped **My stack**, **Automation** and **Starter tech roles**,
  about 12 at most.
- Each job shows title, company, score, reason, salary if listed, the source ("via RemoteOK")
  and the link.
- The message ends with a link to the Sheet, where the full drafts live.
- If nothing new clears 70, a one-line "nothing new today (X fetched, Y filtered, Z scored)"
  message is sent instead, so silence always means the pipeline broke.
- If a run fails, a short failure notice goes to the same channel, with no stack trace or data.

---

## 6. Secrets and keys you'll create

None of these get committed. Locally they live in `.env` (gitignored), with `.env.example`
committed showing the names only. In CI they are GitHub Actions secrets.

| Name | What | How to get it |
|---|---|---|
| `GEMINI_API_KEY` | LLM | aistudio.google.com → Get API key → create in a new project. Don't attach billing. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Sheets write | console.cloud.google.com → new project → enable **Google Sheets API** → IAM → Service accounts → create → Keys → add JSON key. Paste the whole JSON as the secret. |
| `SHEET_ID` | Tracker | Create a blank Google Sheet, share it (Editor) with the service account email, and copy the id from its URL. |
| `SLACK_WEBHOOK_URL` | Digest | slack.com → create a free workspace (e.g. "job-agent") with a `#jobs` channel → api.slack.com/apps → **Create New App** → From scratch → **Incoming Webhooks** → On → **Add New Webhook to Workspace** → pick `#jobs` → copy the URL. Then install the Slack phone app and turn on notifications for `#jobs`. |
| `CANDIDATE_PROFILE` | Scoring input | `python -m jobagent profile` prints the stripped resume text. Paste it into the secret. |

`GITHUB_TOKEN` is built in, so there's nothing to create for it. I'll add a `scripts/setup_secrets.sh`
walkthrough that calls `gh secret set` for each secret, so the values never touch the repo or shell history.

---

## 7. Tests and dry-run

- `pytest` covers:
  - Parsers: each source against a trimmed real fixture, saved from today's responses.
  - Location rules: a table of about 40 real location strings, each with its expected
    pass or drop.
  - Category and seniority rules.
  - URL canonicalization and fingerprint dedupe.
  - The LLM JSON validator, including malformed outputs taken from the old
    `failed_response_*.json` files.
  - Digest formatting and the length cap.
- No network in tests. LLM, Sheet and Slack are behind small interfaces with fakes.
- `tests.yml` runs pytest on every push. Locally, one test run at a time.
- `--dry-run` fetches, filters, dedupes (against local state) and scores. It prints
  the would-be Sheet rows and the digest, but writes nothing and sends nothing.
- `--local` is a dry-run that also records rows and seen ids in `~/.config/job-agent/state/`, so
  cross-run dedupe can be checked before any Google account exists.
- `--no-llm` skips scoring, for zero-cost runs. `--limit N` caps how many jobs are sent to
  the LLM.

---

## 8. Milestones (each one runs end to end)

| # | Milestone | Proof it works |
|---|---|---|
| M0 | Fresh branch from `main`. Remove old modules. Scaffold the package, `pyproject.toml`, `.gitignore` (adds `.env`, `config.local.toml`, `.state/`, `*.pdf`, `failed_response*`), `.env.example`. Add the CLI skeleton and pytest. | `python -m jobagent run --dry-run --no-llm` prints "0 sources". Pytest is green. |
| M1 | Five source adapters + Job model + fixtures + parser tests | Dry-run prints per-source counts from live data. |
| M2 | Filters + dedupe + tests | Dry-run prints kept jobs with category and location rule, plus a "dropped because" summary. |
| M3 | Profile extraction + LLM scoring/drafting (Gemini, then fallback check) | `--dry-run --limit 5` prints scores, reasons and drafts for 5 real jobs. |
| M4 | Google Sheet writer + Sheet-based cross-run dedupe | A real run fills the Sheet. A second run adds 0 duplicate rows. |
| M5 | Slack digest | A real digest arrives in `#jobs` on your phone. |
| M6 | `daily.yml` (cron + manual trigger + keepalive) + `tests.yml` + secrets script | A manual Actions run fills the Sheet and sends the digest without your Mac. |
| M7 | Portfolio README (what, architecture diagram, setup, sample digest screenshot with personal bits blurred), cleanup | README reviewed. Then, with your go-ahead: delete the old experiment branch, push, make the repo public. |

Commits are small, with short imperative subjects. Nothing is pushed until the owner says so.

v2 is built in a separate git worktree cut from `main`, so the old experiment branch stays
untouched.

---

## 9. Choices (settled)

1. Digest channel: **Slack incoming webhook** (Telegram needs a VPN in Pakistan).
2. Threshold for drafts and the digest: **70**. It's a config value, so changing it later
   is one line.
3. Senior titles: **kept**, scored by the LLM against my actual experience.
4. Automation gigs: **in the digest**, as their own section, **and in the Sheet**.
5. Scope: **any tech role I could start in and learn on**, not only full-stack (added
   2026-11-25). Three categories: `stack`, `automation`, `tech-entry`.

---


## 10. Build order and sessions

One build lane, run in order. The work is split into **sessions** so that each one starts
with a small context. A new session reads this plan and the progress log below, and the
code itself is the rest of the hand-off.

| Session | Milestones | What the owner does before or during it | Ends when |
|---|---|---|---|
| 1 | Plan + M0 | Approve the plan | Contracts, dry-run CLI and tests are committed ✅ |
| 2 | M1 sources + M2 filters/dedupe | Nothing. Optionally create the Gemini key (step A below) | A dry-run prints real, filtered, deduped jobs from all five sources ✅ |
| 3 | M3 LLM scoring + drafts | **Step A done before starting** | `--dry-run --limit 5` shows real scores, reasons and drafts |
| 4 | M4 Sheet + M5 Slack | **Steps B and C done before starting** | Rows land in the real Sheet and a digest arrives in Slack |
| 5 | M6 GitHub Actions + M7 README, publish | Step D during the session, then approve the push and publishing | The daily run works with the Mac off, and the repo is public |

### Owner steps (each one is done in a browser; values go in `~/.config/job-agent/.env`)

Never paste a key into a chat. Open the file with
`open -e ~/.config/job-agent/.env`, paste the value after the `=`, and save.

- **A. Gemini key, about 5 minutes.**
  1. Go to aistudio.google.com and sign in.
  2. Click **Get API key** → **Create API key** and let it create a new project.
  3. Copy the key into `GEMINI_API_KEY=`.
  4. Don't add a billing account. Without one, it can't charge.
- **B. Google Sheet + service account, about 20 minutes.** Session 4 walks through it click
  by click. Outline:
  1. console.cloud.google.com → new project `job-agent`.
  2. Enable the **Google Sheets API**.
  3. IAM & Admin → Service accounts → Create, then Keys → Add key → JSON. Open the
     downloaded file in TextEdit, copy everything, and paste it into
     `GOOGLE_SERVICE_ACCOUNT_JSON=` as one line. Then delete the downloaded file.
  4. Create a blank Google Sheet named "Job tracker". Share it as Editor with the service
     account's email (it ends in `iam.gserviceaccount.com`).
  5. Copy the long id from the Sheet's URL (between `/d/` and `/edit`) into `SHEET_ID=`.
- **C. Slack webhook, about 10 minutes.**
  1. Create a free Slack workspace with a `#jobs` channel.
  2. api.slack.com/apps → Create New App → From scratch.
  3. Incoming Webhooks → On → Add New Webhook → `#jobs`.
  4. Copy the URL into `SLACK_WEBHOOK_URL=`.
  5. Install the Slack phone app and turn on notifications for `#jobs`.
- **D. GitHub secrets, about 5 minutes, in session 5.** Run one script that copies the
  values from `~/.config/job-agent/.env` into the repo's Actions secrets with
  `gh secret set`. The values are never printed.

### Rules every session follows

- Work on a branch cut from the previous session's branch. Never push without the owner's
  go-ahead.
- Run one test command at a time: parallel runs have crashed this Mac.
- Before finishing, commit, then update the progress log below: what's done, what's next,
  and any surprises.

## 11. Progress log

- **Session 1 (2026-11-25): Plan + M0 done.**
  - Branch `v2`: contracts (`models.py`, `interfaces.py`), pipeline, dry-run/`--local`
    CLI, local stand-ins and 31 tests.
  - All local secrets and settings live in `~/.config/job-agent/`, outside the repo.
    `config.toml` already points at the resume, and `.env` has empty slots for the keys.
  - `filters.py` and `dedupe.py` are deliberate stubs that keep everything.
  - Raw feeds saved on 2026-11-25 are in `/tmp/jobsrc/*.out`, useful for test fixtures,
    but `/tmp` may be cleared, so re-fetch them if they're gone.
  - **Next: session 2, M1 + M2.**
- **Session 2 (2026-11-25): M1 sources + M2 filters/dedupe done.**
  - Branch `claude/v2-session2-c0ec9f` (cut from `v2` at `8da75aa`). 238 tests pass.
  - **Sources** (`jobagent/sources/`): himalayas, wwr, remoteok, remotive, hn, registered in
    that priority order. Each has a pure `parse(payload)` tested against trimmed fixtures in
    `tests/fixtures/`, plus a thin `fetch`. Shared helpers are in `sources/_util.py`.
  - **Filters** (`filters.py`): `evaluate`, `location_rule`, `work_authorization_lock`,
    `required_years` (not used yet: session 3 passes it to the LLM as a hint). Drop labels are
    `DROP_LABELS` = non-tech, seniority, location, work-authorization.
  - **Dedupe** (`dedupe.py`): id or company+title fingerprint; first source wins, others go to
    `also_on`.
  - **Live dry-run, 2026-11-25:** fetched himalayas=391, wwr=381, remoteok=100, remotive=15,
    hn=238 (1,125 total, ~18 s). 368 passed the filters, 15 duplicates, 353 new. Kept per
    source: himalayas 246, wwr 87, hn 13, remotive 4, remoteok 3. Categories: tech-entry 216,
    stack 112, automation 25. Location rule: worldwide 217, pakistan 120, asia 12, emea 3,
    unspecified 1. Dropped: non-tech 346, location 292, seniority 110, work-authorization 9.
    A second `--local` run reported all 353 as already seen.
  - **Contract change:** `RunOptions.track_unscored` (default False) in `pipeline.py`. Unscored
    jobs are never tracked, so `--local --no-llm` could never show cross-run dedupe working.
    The CLI sets the flag only for `--local --no-llm`. Production behavior is unchanged.
  - **Surprises:**
    - WWR's `<country>` field is a real restriction: "Anywhere in the World" plus a country
      means "only these countries". Its board category is often wrong (statisticians filed under
      Full-Stack), so it's not used as a tag.
    - Source tags are too noisy to prove a role is technical: the title decides.
    - Remote OK and HN add little: 64 of 100 Remote OK jobs are US-only, and most HN posts are
      US-remote or onsite. A bare HN "REMOTE" is dropped, per section 2.
    - Same job on two boards is rare (1 today). Most duplicates are reposts within one board.
    - A few Himalayas "talent pool" companies (Hivex, micro1, Xperteez) post many near-identical
      jobs. The scorer should rank those low.
    - `test_cli_dry_run_with_no_sources` was hitting the live sites once sources existed. It now
      patches the registry empty.
  - **Next: session 3, M3.** Needs owner Step A (Gemini key) first, and must be cut from this
    branch.
- **Session 3 (2026-11-25): M3 LLM scoring + drafts done.**
  - Branch `claude/v2-session3-b32d99` (cut from `claude/v2-session2-c0ec9f` at `2c12084`). 306 tests pass.
  - **Profile** (`profile.py`): pypdf in layout mode (plain mode gave one word per line), then
    `strip_contacts` removes emails, phones, URLs, bare domains (LinkedIn, GitHub, the company
    site) and the name line, which becomes "The candidate". `CANDIDATE_PROFILE` wins when set.
    `python -m jobagent profile` prints the stripped text for the session 5 secret. Checked on the
    real resume with counts only: 0 emails, phones, links or name parts left, ~900 tokens.
  - **Model: `gemini-3.1-flash-lite`** (override with `GEMINI_MODEL`). `models.list` on the owner's
    key lists it, stable, 1,048,576 input / 65,536 output tokens. It is the cheapest current,
    stable Flash-class model that's open to new users (`gemini-2.5-flash-lite` is cheaper but
    limited to existing users, and `gemini-2.5-flash` is retired on 2026-12-01). Calls succeed
    with no billing on the key.
  - **Free-tier limits could not be confirmed:** the docs say per-model RPM/TPM/RPD are only shown
    in AI Studio (aistudio.google.com/rate-limit), and responses carry no limit headers. So the
    client paces at 6 s between calls (10 per minute), retries a 429/5xx once after a short wait
    (server delay, capped at 20 s), and gives up at once when Google asks for a longer wait (daily
    quota gone). Thinking is set to "minimal". This session used about 15 requests.
  - **Fallbacks:** chain = configured provider, then the other hosted one with credentials, then
    unscored. A provider that hits 429 after its retry, or a 4xx, is skipped for the rest of the
    run. **GitHub Models is implemented but not verified live:** from this Mac, `models.github.ai`
    answers every request (catalog and chat) with a bare `200 OK` text body, and the `gh` login
    token has no `models` scope anyway. Verify it in session 5 from Actions (`permissions: models:
    read`, `GITHUB_TOKEN`). **Ollama** is implemented (`LLM_PROVIDER=ollama`) but untested: not
    installed here.
  - **Scorer** (`scorer.py`, prompts in `prompts/`): batches of 10 with short ids (`j1`...) mapped
    back to real ids, JSON mode with a schema. The validator drops bad items (unknown or duplicate
    ids, scores out of 0-100, empty reasons), accepts `"85"` and `85.0`, strips fences and prose,
    and salvages complete items from truncated JSON. Unusable output: one retry, then the next
    provider. `category` and `location_rule` are recomputed with `filters.evaluate` inside the
    scorer, so the `Scorer` contract didn't change.
  - **Quality notes from the live runs** (`--limit 5`, `--limit 20`, and a hand-picked batch of 10):
    - Junior React/full-stack roles scored 75-85. The Customer.io senior backend role (7+ years)
      scored 25. All Hivex, micro1 and Xperteez posts scored 25-30. Philippines-only and US-locked
      jobs that slipped past the filters were caught at 30.
    - The model once ignored the 7+ years cap (it gave 40), so the 5+ (40) and 7+ (25) caps are
      now also enforced in code after scoring (`apply_caps`).
    - Drafts: every skill and project they cite was checked against the profile. Missing skills
      are framed as "new to me". Early drafts added a time-zone claim, generic padding ("managing
      state") and filler endings, so `draft.txt` now bans those. Notes land at 105-115 words.
  - **Settings added** (`config.py`, all optional): `GEMINI_MODEL`, `GITHUB_MODELS_TOKEN` (falls
    back to `GITHUB_TOKEN`), `GITHUB_MODELS_MODEL`, `OLLAMA_MODEL`, `OLLAMA_URL`,
    `SCORE_BATCH_SIZE`, `MAX_DRAFTS`, `DESCRIPTION_CHARS`, `MAX_SCORED_PER_RUN` (default 100,
    which is now the default `--limit` when the LLM is on, so the ~350-job backlog spreads over
    about 4 days).
  - The `llm.py` in section 1's layout became a package: `jobagent/llm/` (base, gemini,
    github_models, ollama).
  - **Next: session 4, M4 + M5.** Needs owner Steps B and C first, and must be cut from this
    branch.
