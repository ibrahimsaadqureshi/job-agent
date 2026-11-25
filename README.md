# Job Agent

A free daily pipeline that finds remote tech jobs open to candidates in Pakistan, scores
them against a resume with a free LLM, drafts short application notes, tracks everything in
a Google Sheet and sends one Slack digest a day. A human reviews every job and applies by
hand: there is no auto-apply.

> **v2 is under construction.** The design and milestones are in [PLAN.md](PLAN.md). A full
> README with architecture, setup and a sample digest arrives in milestone M7.

## Quick start (development)

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python -m jobagent run --dry-run --no-llm
```

## Layout

```
jobagent/
  models.py       Job, Verdict, Assessment, Candidate, TrackerRow, Sheet columns, job ids
  interfaces.py   Source, Scorer, Tracker, Notifier protocols + Digest
  pipeline.py     fetch -> filter -> dedupe -> score -> draft -> track -> digest
  filters.py      category / location / seniority rules        (M2)
  dedupe.py       in-run duplicate collapsing                    (M2)
  digest.py       pick and render the daily digest
  local.py        local-state tracker + console notifier for dry and local runs
  config.py       env vars + ~/.config/job-agent/ (secrets and local settings, outside the repo)
  net.py          shared HTTP session (honest User-Agent, timeout, retry)
  cli.py          python -m jobagent run [--dry-run | --local] [--no-llm] [--limit N] [--sources a,b]
  sources/        one module per job board                       (M1)
tests/            pytest, no network; fakes.py has in-memory versions of every interface
```
