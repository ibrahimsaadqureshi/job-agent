# Job Agent

A local-first AI-powered job discovery, ranking, and application intelligence platform designed to identify the highest-value opportunities and improve application quality through structured evaluation and automation.

## Overview

Job Agent aggregates jobs from multiple sources, stores them in SQLite, ranks them based on relevance, evaluates resume-job fit using local AI models, and surfaces the best opportunities for review.

The project is designed around quality over quantity.

Goal:

Sources
↓
Central Database
↓
Relevance Ranking
↓
AI Assessment Layer
↓
Evaluation Framework
↓
Top Opportunities Report
↓
Resume Intelligence
↓
Recruiter Outreach
↓
Assisted Applications

## Current Features

### Job Sources

Implemented:

* YC Jobs
* Greenhouse
* RemoteOK

Planned:

* Ashby
* Lever
* HN Who's Hiring

### Database

* SQLite storage
* URL-based deduplication
* Unified job schema

Schema:

* id
* title
* company
* location
* url
* source
* description
* score
* matched
* reviewed
* date_found

### Description Extraction

Descriptions are extracted and normalized from all supported sources:

* YC job pages
* Greenhouse Boards API
* RemoteOK API

### Ranking Engine

Current ranking factors include:

* Positive keyword scoring
* Role bonuses
* Junior/new-grad bonuses
* Seniority penalties
* Experience requirement penalties
* Role-fit scoring
* Description-aware relevance matching

### AI Assessment Layer

Implemented:

* Local Ollama integration
* Qwen2.5:7b support
* Resume vs Job Description assessment
* Structured JSON output
* Match scoring
* Strength extraction
* Transferable skill extraction
* Missing skill analysis
* Recruiter talking points
* Batch assessment processing
* Assessment persistence
* Retry handling
* Schema validation

### Assessment Evaluation Framework

Implemented tools:

* run_eval.py
* compare_eval.py
* consistency_check.py

Capabilities:

* Assessment snapshot generation
* Score drift analysis
* Ranking stability analysis
* Skill consistency analysis
* Prompt experimentation

Key findings:

* Match scores are relatively stable across runs.
* Job rankings are relatively stable across runs.
* The primary challenge is evidence attribution rather than score stability.
* Prompt engineering alone does not fully eliminate unsupported tool-specific inferences.

### Reporting

Available reports:

* Source counts
* Sample jobs
* Top ranked jobs
* AI assessment rankings

Top jobs reporting includes report-level duplicate suppression.

## Technology Stack

Core:

* Python
* SQLite
* Ollama
* Qwen2.5:7b

Development:

* Git
* GitHub

Environment:

* Pop!_OS
* Python virtual environment

## Current Architecture

Sources
↓
Normalization
↓
SQLite Database
↓
Ranking Engine
↓
AI Assessment Layer
↓
Evaluation Framework
↓
Reports

Database location:

database/jobs.db

## Current Status

### Phase 1 — Complete

* Database
* Scrapers
* Deduplication
* Data validation

### Phase 2 — Complete

* Ranking engine
* Relevance scoring
* Reporting

### Phase 2.5 — Complete

* Experience-aware ranking
* Seniority penalties
* Junior bonuses
* Role-fit scoring
* Duplicate investigation
* Report deduplication

### Phase 3.1 — Complete

* Local Ollama integration
* Assessment generation
* JSON validation
* Retry handling

### Phase 3.2 — Complete

* Batch assessment processing
* Assessment persistence
* Match score ranking

### Phase 3.2.1 — Complete

* Detailed ranking output
* Strength summaries
* Missing skill summaries
* Recruiter-focused summaries

### Phase 3.3 — Complete

* Assessment evaluation framework
* Assessment comparison tooling
* Consistency checking
* Prompt experimentation
* Schema experimentation
* Stability analysis

Key result:

Assessment scores are reasonably stable.

The primary remaining challenge is evidence attribution and explainability.

### Current Focus — Phase 3.4

Evidence-Based Assessments

Goals:

* Explain assessment reasoning
* Attach evidence to strengths
* Improve trustworthiness
* Reduce unsupported tool-specific claims
* Improve recruiter-style recommendations

## Future Roadmap

### Phase 3.4

Evidence-Based Assessments

### Phase 2.6

Additional Sources

* Ashby
* Lever
* HN Who's Hiring

### Phase 4

Streamlit Dashboard

Features:

* Job browser
* Search
* Filters
* AI match scores
* Saved jobs

### Phase 5

n8n + WhatsApp Notifications

Python
↓
SQLite
↓
n8n
↓
WhatsApp

### Phase 6

Feedback Learning

* Apply
* Save
* Skip

### Phase 7

Resume Tailoring

* Missing keywords
* Resume recommendations
* Role-specific improvements

### Phase 8

Recruiter Outreach

* Company research
* Recruiter talking points
* Outreach assistance

### Phase 9

Assisted Applications

Supported:

* Greenhouse
* Lever

Human review required.

## Design Philosophy

The objective is not maximum application volume.

The objective is:

* Better targeting
* Better fit
* Better resume alignment
* Higher quality opportunities
* Faster applications
* Higher interview conversion

Quality over quantity.
