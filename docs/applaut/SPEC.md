> **Applaut product spec.** Moved here from the repo-root `CLAUDE.md` (Oct 2026)
> when that file became the LVAMO master spec. Platform-wide rules (tech stack,
> security, vertical separation) now live in `CLAUDE.md`; where the two
> overlap, `CLAUDE.md` wins. Content below is unchanged.

# APPLAUT\_MASTER\_SPEC.md

Project: Applaut
Business Brand: LVAMO

## PURPOSE

This document is the single source of truth for Claude Code.

Your responsibility is implementation.

If implementation details are missing, make the smallest reasonable assumption and document it.

\---

# PRODUCT VISION

Applaut is an AI-powered application automation platform.

Goal:

Reduce job application effort from hours per day to 10–20 minutes per day.

The platform should:

1. Discover jobs automatically.
2. Match jobs against a user's profile.
3. Generate tailored resumes.
4. Generate tailored cover letters.
5. Assist with applications.
6. Track applications.
7. Continuously improve relevance.

The system prioritizes quality over quantity.

Success is measured by:

Applications Submitted / Jobs Found

Higher quality matches are preferred over large numbers of weak matches.

\---

# TARGET USER

Example:

Data Engineer in Berlin on Opportunity Card Visa.

Limited time.

Needs:

* Fast discovery
* Relevant opportunities
* Tailored documents
* Reduced manual effort

The platform should eventually support any profession.

\---

# USER JOURNEY

1. User lands on website.
2. User selects:
* Login
* Register
* Google Login
3. User creates account.
4. User enters:
* Name
* Email
* Experience
5. User selects:
* Countries (multi-select)
* Remote option
* Employment types
* Roles
6. User uploads master resume.
7. AI extracts:
* Skills
* Experience
* Certifications
* Education
8. User verifies extracted data.
9. User chooses automation duration.
10. Discovery begins.
11. Dashboard displays:
* Jobs found
* Scores
* Documents generated
* Applications

\---

# CORE PRINCIPLES

1. Cloud First
2. Multi User
3. AI Assisted
4. Explainable Decisions
5. Auditability
6. Human Approval First
7. Provider Agnostic

\---

# TECHNOLOGY STACK

Frontend

* React
* Vite
* TypeScript

Backend

* Python
* FastAPI

Database

* PostgreSQL

Storage

* Cloudflare R2

Hosting

* Oracle Cloud VM

Frontend Hosting

* Cloudflare Pages

Automation

* Playwright

Scheduling

* APScheduler

AI

Provider abstraction required.

Initial provider:

* OpenAI

Future:

* Claude
* Gemini

\---

# ARCHITECTURE

Frontend
↓
FastAPI Backend
↓
Business Services
↓
PostgreSQL
↓
Cloudflare R2

Every major component must be replaceable.

\---

# USER PROFILE MODEL

Store:

* Name
* Email
* Experience
* Skills
* Education
* Certifications
* Countries
* Roles
* Employment Preferences

Future:

Multiple profiles per user.

\---

# DISCOVERY ENGINE

Version 1 Sources

* Greenhouse
* Lever
* Ashby
* Personio

Future Sources

* Workday
* LinkedIn
* StepStone
* Indeed
* Xing

Use adapter pattern.

Never hardcode source-specific logic throughout the system.

\---

# LOCATION MATCHING

User selects countries.

Examples:

Germany
Netherlands
Austria

The system must understand:

Berlin → Germany
Munich → Germany

Location qualification must operate at country level.

\---

# SCORING ENGINE

Score Range

0-100

Inputs

* Skills
* Experience
* Location
* Employment Type
* Education
* Languages

Every score must contain explanation.

No black-box decisions.

\---

# DOCUMENT GENERATION

Input

* Master Resume
* Job Description

Output

* Tailored Resume
* Tailored Cover Letter

Rules

Never invent information.

Allowed:

* Reordering
* Rephrasing
* Prioritization

Forbidden:

* Inventing skills
* Inventing experience
* Inventing certifications

\---

# APPLICATION ENGINE

Default Mode

Review Mode

User reviews before submission.

Future

Auto Apply

Must be optional.

\---

# VERSION 1 APPLICATION STRATEGY

For ATS systems:

* Prefill fields
* Upload generated documents
* Navigate forms

User performs final review and submit.

\---

# DATABASE RULES

Design database for:

* Multi User SaaS
* Auditability
* Scalability

Expected entities:

* users
* profiles
* resumes
* opportunities
* scores
* applications
* generated\_documents
* notifications
* audit\_logs

Claude should design detailed schema.

\---

# API RULES

Use REST.

Version all endpoints.

Base:

/api/v1

Claude should design endpoint contracts.

\---

# SECURITY RULES

Required:

* JWT
* Password Hashing
* HTTPS

Never store secrets in source code.

\---

# STORAGE RULES

Store in R2:

* Resumes
* Cover Letters
* Screenshots
* Artifacts

Store metadata in PostgreSQL.

\---

# IMPLEMENTATION EXPECTATIONS

Claude must:

1. Create complete folder structure.
2. Create database schema.
3. Create migrations.
4. Create backend.
5. Create frontend.
6. Create deployment configuration.
7. Create tests.
8. Create documentation.

Do not wait for instructions file-by-file.

Implement complete vertical slices.

\---

# WHEN CODE CHANGES ARE REQUIRED

Always provide:

* File path
* Full file contents

Never provide partial patches.

Never provide only changed snippets.

\---

# FORBIDDEN ARCHITECTURAL CHANGES

Do not replace:

* FastAPI
* PostgreSQL
* React
* R2
* Oracle VM

without explicit approval.

\---

# END GOAL

Deliver a production-ready SaaS platform capable of becoming the public product:

LVAMO

while maintaining clean architecture, explainability, auditability and scalability.

