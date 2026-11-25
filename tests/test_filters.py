"""Filter rules (PLAN.md section 3), tested on real titles and locations seen on 2026-11-25."""

from __future__ import annotations

import pytest

from jobagent import filters
from jobagent.filters import LOCATION, NON_TECH, SENIORITY, WORK_AUTHORIZATION
from jobagent.models import Category
from fakes import make_job

STACK, AUTOMATION, ENTRY = Category.STACK, Category.AUTOMATION, Category.TECH_ENTRY


def verdict_for_title(title: str):
    return filters.evaluate(make_job(title=title, description="", location="Worldwide", source="wwr", tags=()))


# --- Titles ---------------------------------------------------------------------------

TITLES = [
    # kept, with their digest section
    ("Senior Software Engineer, Backend", ENTRY),
    ("Technical Support Engineer I", ENTRY),
    ("Frontend Software Engineer, Personal Loans", STACK),
    ("Full Stack Product Software Engineer", STACK),
    ("Senior Fullstack Developer (React.js / Node.js)", STACK),
    ("Backend Developer (NestJS)", STACK),
    ("Senior React Native & React Engineer PK", STACK),
    ("React Native Developer", ENTRY),  # mobile: tech-entry unless plain React is named too
    ("PHP developer", ENTRY),
    ("Flutter Developer", ENTRY),
    ("Senior QA Automation Engineer (Platform)", ENTRY),  # test automation is QA, not n8n-style automation
    ("Site Reliability Engineer", ENTRY),
    ("Machine Learning Engineer", ENTRY),
    ("Senior Data Engineer", ENTRY),
    ("Tier III Service Desk Engineer", ENTRY),
    ("MSP Mac Help Desk Guru (work from home)", ENTRY),
    ("Cloud Systems Administrator", ENTRY),
    ("Web Developer: WordPress & HubSpot", AUTOMATION),
    ("Automations & Data Analytics Specialist", AUTOMATION),
    ("Solution and Implementation Engineer", ENTRY),
    ("Member of Technical Staff (Storage)", ENTRY),  # an IC title, not staff level
    ("Senior/Staff Software Engineer", ENTRY),  # open at Senior too
    ("Frontend Engineer, Ads Campaign Manager", STACK),  # "Campaign Manager" is the product
    ("Software Engineer Intern", ENTRY),
    ("JUNIOR SERVICENOW CONSULTANT – GRC (x2)", ENTRY),
    ("Senior Shopify Developer (Remote + Flexible)", ENTRY),
    ("Remote Full-Stack Django/React Developer (Non-US/Non-EU Position) - FULLY REMOTE", STACK),
    ("Agentic Python Engineer", ENTRY),
    ("AI Automation Expert (n8n / Make / Zapier / AI Agents)", AUTOMATION),
    ("GHL Specialist", AUTOMATION),
    ("CRM Specialist", AUTOMATION),
    ("Marketing Automation Specialist", AUTOMATION),  # automation beats the "marketing" drop
    ("QA Engineer - Mid Level (Automation Focus)", ENTRY),
    # dropped: not a tech role
    ("Field Marketing Coordinator, Upmarket", NON_TECH),
    ("Senior TA Operations Specialist", NON_TECH),
    ("AP - Property Accountant (NZ experience)", NON_TECH),
    ("Sets&Props Concept Artist Internship", NON_TECH),
    ("Corporate Counsel, Commercial", NON_TECH),
    ("SEA P2P Business Development Specialist", NON_TECH),
    ("Real Estate Executive Assistant 21370", NON_TECH),
    ("Customer Service Representative", NON_TECH),
    ("Inside Sales Contractor", NON_TECH),
    ("Freelance Copywriter", NON_TECH),
    ("Remote Office Assistant", NON_TECH),
    ("Founding Sales (Founding AE)", NON_TECH),
    ("Brand Identity Designer (AI-agent team)", NON_TECH),
    ("Product Designer", NON_TECH),
    ("Mechanical Design Engineer", NON_TECH),  # engineering, but not software
    ("Civil Quantity Surveyor", NON_TECH),
    ("PhD in AI / Earth Observation / Environmental Science", NON_TECH),
    ("Sr. Statistician, Client Intelligence", NON_TECH),
    ("Complaints Analyst III", NON_TECH),
    ("Customer Success Manager", NON_TECH),
    ("Junior Video Editor: Direct Response Ads", NON_TECH),
    ("Principal Executive Recruiter, R&D", NON_TECH),
    ("Language Alignment & Resource Partner (Korean) - Freelance AI Trainer Project", NON_TECH),
    ("German Speaker - AI Trainer", NON_TECH),
    ("AI GTM Lead", NON_TECH),
    ("ROBOTICS ENGINEER", NON_TECH),
    # dropped: too senior (Senior itself is kept, above)
    ("Staff Software Engineer", SENIORITY),
    ("Senior Manager, Enterprise Application Development Engineering", SENIORITY),
    ("Principal Software Engineer - React", SENIORITY),
    ("Engineering Manager - Python and K8s", SENIORITY),
    ("Director, Engineering", SENIORITY),
    ("Head of Technology", SENIORITY),
    ("Field CTO, AI Factory", SENIORITY),
    ("Staff Backend Engineer, Performance Enablement", SENIORITY),
    ("Senior Technical Product Manager", SENIORITY),
    ("Revenue Operations Manager", SENIORITY),
    ("Founding Staff / Principal Engineer", SENIORITY),
    # dropped: region lock written into the title
    ("Senior QA Engineer - Europe", LOCATION),
    ("AI/ML Engineer - Production AI & LLM Systems (India)", LOCATION),
    ("Senior Customer Engineer - LATAM (Spanish Speaking)", LOCATION),
    ("Web Developer: WordPress & HubSpot (U.S. Based, Remote Contractor)", LOCATION),
]


@pytest.mark.parametrize("title, expected", TITLES)
def test_title_rules(title, expected):
    v = verdict_for_title(title)
    if isinstance(expected, Category):
        assert v.keep, f"dropped as {v.reason}"
        assert v.category == expected
    else:
        assert not v.keep and v.reason == expected


def test_title_table_is_big_enough():
    assert len(TITLES) >= 40


def test_word_boundaries_not_substrings():
    # "ai" in "maintain", "go" in "good", "java" in "javascript": none may match on their own.
    assert verdict_for_title("Maintainer of Good Things").reason == NON_TECH
    assert filters._words("ai").search("maintain") is None
    assert filters._words("java").search("javascript") is None
    assert filters._words(r"c\+\+").search("C++ Systems Engineer")
    assert filters._words(r"\.net").search("Senior .NET Developer")


def test_stack_category_from_tags_and_description():
    job = make_job(title="Software Engineer", tags=("typescript", "react"), description="", location="Worldwide")
    assert filters.evaluate(job).category == STACK
    job = make_job(title="Software Engineer", tags=(), description="We use React and TypeScript.", location="Worldwide")
    assert filters.evaluate(job).category == STACK
    job = make_job(title="Software Engineer", tags=(), description="Go services, a little React.", location="Worldwide")
    assert filters.evaluate(job).category == ENTRY  # one stack word is not enough
    job = make_job(title="Integration Engineer", description="", location="Worldwide")
    assert filters.evaluate(job).category == AUTOMATION
    job = make_job(title="Software Engineer", description="Build n8n and Zapier flows.", location="Worldwide")
    assert filters.evaluate(job).category == AUTOMATION


def test_infrastructure_automation_tag_is_not_the_automation_category():
    job = make_job(title="Senior DevOps Engineer (Puppet)", tags=("automation", "devops"), description="", location="Worldwide")
    assert filters.evaluate(job).category == ENTRY


def test_tags_alone_do_not_make_a_title_technical():
    job = make_job(title="Senior Tax Associate", tags=("technical", "sys admin"), description="", location="Worldwide")
    assert filters.evaluate(job).reason == NON_TECH


def test_hn_post_without_role_is_judged_by_text():
    tech = make_job(source="hn", title="See post", location="REMOTE (Worldwide)", description="We need backend engineers (Python).")
    assert filters.evaluate(tech).keep
    nontech = make_job(source="hn", title="See post", location="REMOTE (Worldwide)", description="We are hiring a bookkeeper.")
    assert filters.evaluate(nontech).reason == NON_TECH
    mixed = make_job(source="hn", title="engineering, GTM, product, sales", location="SF Bay, Toronto, APAC, Remote")
    assert filters.evaluate(mixed).keep
    assert verdict_for_title("Sales / Account Executive GovTech").reason == NON_TECH
    multi = make_job(source="hn", title="Multiple Positions", location="REMOTE (Worldwide)", description="Software engineers wanted.")
    assert filters.evaluate(multi).keep


def test_research_roles_needing_a_phd_are_dropped():
    job = make_job(title="Research Engineer", description="A PhD in ML is required.", location="Worldwide")
    assert filters.evaluate(job).reason == NON_TECH


# --- Locations ------------------------------------------------------------------------

LOCATIONS = [
    # passes
    ("Worldwide", "worldwide"),
    ("Anywhere in the World", "worldwide"),
    ("REMOTE (worldwide, any timezone)", "worldwide"),
    ("REMOTE (Worldwide)", "worldwide"),
    ("100% Remote (Global)", "worldwide"),
    ("REMOTE worldwide", "worldwide"),
    ("REMOTE(World) / Brno, Czech Republic", "worldwide"),
    ("REMOTE (anywhere, EST hours)", "worldwide"),
    ("REMOTE, ALMOST ANYWHERE", "worldwide"),
    ("REMOTE (Worldwide, Berlin timezone overlap preferred)", "worldwide"),
    ("Asia Only", "asia"),
    ("Asia", "asia"),
    ("LATAM, Europe, USA, Canada, APAC", "asia"),
    ("REMOTE (Europe, Africa, W Asia)", "asia"),
    ("SF Bay, Toronto, APAC, Remote", "asia"),
    ("EMEA", "emea"),
    ("EMEA Only", "emea"),
    ("Pakistan", "pakistan"),
    ("Egypt, India, Pakistan", "pakistan"),
    ("", "unspecified"),
    ("Remote", "unspecified"),
    ("Fully REMOTE", "unspecified"),
    ("Remote possible", "unspecified"),
    # drops (None)
    ("US Only", None),
    ("USA Only", None),
    ("Europe Only", None),
    ("Canada Only", None),
    ("UK Only", None),
    ("Latin America", None),
    ("Oceania Only", None),
    ("Africa Only", None),
    ("North America Only", None),
    ("Philippines", None),
    ("Newark", None),
    ("München", None),
    ("Arlington", None),
    ("Remote, EST United States", None),
    ("USA", None),
    ("USA, Canada, USA timezones", None),
    ("Europe, USA, Canada, Australia, Singapore, Mexico, Saudi Arabia", None),
    ("REMOTE (US)", None),
    ("REMOTE (all remote); Hiring GMT-8 to GMT+2", None),
    ("ONSITE", None),
    ("HYBRID", None),
    ("Remote (North America & Europe)", None),
    ("REMOTE (CET)", None),
    ("India (REMOTE / ONSITE)", None),
    ("UK time zone", None),
    ("Remote (US/EU timezones preferred)", None),
    ("On-site in Stockholm, Sweden", None),
    ("REMOTE (most countries)", None),
    ("Berlin, Germany (or remote, CET overlap)", None),
]


@pytest.mark.parametrize("location, expected", LOCATIONS)
def test_location_rules(location, expected):
    assert filters.location_rule(make_job(location=location)) == expected


def test_location_table_is_big_enough():
    assert len(LOCATIONS) >= 40


@pytest.mark.parametrize(
    "location, expected",
    [
        ("UTC+3 to UTC+6", "timezone"),
        ("GMT+5", "timezone"),
        ("UTC+05:00", "timezone"),
        ("Remote (UTC+4 ± 2h)", "timezone"),
        ("UTC-5 to UTC+1", None),
        ("PKT hours", "pakistan"),
    ],
)
def test_timezone_rules(location, expected):
    assert filters.location_rule(make_job(location=location)) == expected


def test_structured_restrictions_win_over_text():
    assert filters.location_rule(make_job(location="Anywhere in the World (Poland)", location_restrictions=("Poland",))) is None
    assert filters.location_rule(make_job(location="54 countries incl. Pakistan", location_restrictions=("India", "Pakistan"))) == "pakistan"


def test_hn_bare_remote_is_dropped():
    # HN posts that only say REMOTE are nearly always US-remote.
    assert filters.evaluate(make_job(source="hn", title="Software Engineer", location="Remote")).reason == LOCATION
    assert filters.evaluate(make_job(source="remoteok", title="Software Engineer", location="Remote")).location_rule == "unspecified"


# --- Work authorization ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Candidates must be authorized to work in the United States.",
        "Legally eligible to work in the U.S. on an ongoing basis.",
        "Must be legally authorized to work in the US.",
        "Eligibility: Candidates must currently reside in the United States.",
        "This is a remote position. However, candidates must be located in the United States or Canada.",
        "US based applicants only $138,905 — $285,982 USD",
        "REMOTE (US Citizenship Required)",
        "Active security clearance required.",
        "This is a W-2 position.",
    ],
)
def test_work_authorization_phrases_drop(text):
    job = make_job(title="Software Engineer", location="Anywhere in the World", description=text)
    assert filters.evaluate(job).reason == WORK_AUTHORIZATION


@pytest.mark.parametrize(
    "text",
    [
        "Our compensation for US based candidates lies between 48,000 USD and 70,000 USD.",
        "Reddit offers a wide range of benefits to U.S.-based employees.",
        "We are authorized to work in any country through our EOR partner.",
        "Work from anywhere. Must be comfortable with async work.",
    ],
)
def test_work_authorization_false_positives_kept(text):
    job = make_job(title="Software Engineer", location="Anywhere in the World", description=text)
    assert filters.evaluate(job).keep


def test_pakistan_restriction_skips_work_authorization_scan():
    job = make_job(title="Software Engineer", location="Pakistan", location_restrictions=("Pakistan",),
                   description="Benefits for US citizens differ.")
    assert filters.evaluate(job).keep


# --- Years of experience --------------------------------------------------------------


@pytest.mark.parametrize(
    "text, years",
    [
        ("5+ years of experience with React", 5),
        ("3-5 years experience in Node", 3),
        ("Experience Required: 4–8 Years", 4),
        ("at least 4 years in a similar role", 4),
        ("0-2 years", 0),
        ("two years of professional experience", 2),
        ("10+ yrs", 10),
        ("2+ years with TypeScript and 6+ years overall", 6),
        ("Founded 10 years ago, we are 15 years old", None),
        ("No experience needed", None),
    ],
)
def test_required_years(text, years):
    assert filters.required_years(text) == years


def test_drop_labels_are_the_fixed_set():
    assert filters.DROP_LABELS == ("non-tech", "seniority", "location", "work-authorization")
