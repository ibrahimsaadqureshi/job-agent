# Job Agent

A local-first job discovery, ranking, and application intelligence system designed to help identify the highest-value opportunities with minimal manual effort.

## Overview

Job Agent aggregates jobs from multiple sources, stores them in SQLite, ranks them based on relevance, and produces reports that surface the best opportunities for review.

The project is designed around quality over quantity.

Goal:

Sources
↓
Central Database
↓
Relevance Ranking
↓
Top Opportunities Report
↓
Resume Intelligence
↓
Recruiter Outreach
↓
Application Automation

## Current Features

### Job Sources

* YC Jobs
* Greenhouse
* RemoteOK

### Database

* SQLite storage
* URL-based deduplication
* Unified job schema

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

### Reporting

Available reports:

* Source counts
* Sample jobs
* Top ranked jobs

Top jobs reporting includes report-level duplicate suppression.

## Technology Stack

* Python
* SQLite
* Git
* GitHub

Development Environment:

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
Reports

Database location:

database/jobs.db

## Project Status

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

### Phase 3 — Planned

Resume Intelligence using Ollama.

Planned outputs:

* Match score
* Missing skills
* Recruiter summary
* Resume recommendations

### Future Roadmap

Phase 4

* Resume tailoring

Phase 5

* Dashboard and reporting

Phase 6

* Additional job sources

Phase 7

* Recruiter outreach

Phase 8

* Application automation

Phase 9

* Telegram approval workflow

## Design Philosophy

The objective is not maximum application volume.

The objective is:

* Better targeting
* Faster applications
* Stronger fit
* Better resume alignment
* Higher quality opportunities

Quality over quantity.

