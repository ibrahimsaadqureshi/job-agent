"""Filter stage: is this a tech role I could do, and can I apply from Pakistan?

Rules from PLAN.md section 3. Everything is case-insensitive and matches whole
words (never substrings), so "ai" can't match "maintain" and "go" can't match "good".

Order of checks for one job:
1. Category: drop non-tech titles; label the rest stack / automation / tech-entry.
2. Seniority: drop staff, principal, director, head of, VP, C-level and manager titles.
   Senior titles are kept; the scorer weighs them against my experience.
3. Location: pass worldwide / asia / emea / pakistan / timezone (covers UTC+5) /
   unspecified (blank). Drop region-locked jobs.
4. Work authorization: drop descriptions that require US citizenship, a clearance,
   W-2, residence in a named country, and so on.
"""

from __future__ import annotations

import re

from jobagent.models import Category, Job, Verdict

# Drop labels. Counted in RunStats.dropped, so keep this set small and stable.
NON_TECH = "non-tech"
SENIORITY = "seniority"
LOCATION = "location"
WORK_AUTHORIZATION = "work-authorization"
DROP_LABELS = (NON_TECH, SENIORITY, LOCATION, WORK_AUTHORIZATION)

NO_ROLE = "See post"  # title the HN parser uses when a post names no role


def _words(*terms: str) -> re.Pattern[str]:
    """Case-insensitive alternation with word boundaries that also work around
    symbols ("c++", ".net", "next.js"): a term can't touch a letter or digit."""
    body = "|".join(terms)
    return re.compile(rf"(?<![a-z0-9])(?:{body})(?![a-z0-9])", re.IGNORECASE)


# --- Category -------------------------------------------------------------------------

_ENGINEERING = _words(r"engineering", r"eng")
# Separators between alternative roles or levels in one title.
_ALTERNATIVES = re.compile(r"\s*(?:/|,|\+|&|;|\band\b|\bor\b)\s*", re.IGNORECASE)

_AUTOMATION_TERMS = (
    r"n8n", r"zapier", r"make\.com", r"go ?high ?level", r"highlevel", r"ghl",
    r"(?:workflow|business|process|marketing|sales|ai|crm|no-?code|low-?code|revops)[ -]automation",
    r"revops", r"rev ?ops", r"revenue operations", r"crm", r"hubspot", r"salesforce", r"airtable",
    r"low-?code", r"no-?code", r"power automate", r"rpa", r"uipath",
    r"integrations?(?: engineer| developer| specialist)?",
)
# Tags and descriptions say "automation" for infrastructure work too (DevOps, CI), so only
# the specific terms count there; a title saying "Automation Specialist" is enough.
_AUTOMATION = _words(*_AUTOMATION_TERMS)
_AUTOMATION_TITLE = _words(*_AUTOMATION_TERMS, r"automations?")
_QA_TITLE = _words(r"qa", r"test", r"tester", r"testing", r"sdet", r"quality assurance")
_AUTOMATION_TOOLS = _words(r"n8n", r"zapier", r"make\.com", r"go ?high ?level", r"highlevel")  # in descriptions
_QA_AUTOMATION = _words(r"test automation", r"qa automation", r"automation (?:qa|test|tester|testing)")

_STACK = _words(
    r"typescript", r"javascript", r"js", r"react", r"react\.?js", r"next\.?js", r"node", r"node\.?js",
    r"nest\.?js", r"full[- ]?stack", r"front[- ]?end", r"mongo(?:db)?", r"mern",
)
_STACK_DESCRIPTION = _words(r"typescript", r"react", r"react\.?js", r"next\.?js", r"node\.?js", r"nest\.?js", r"mern")
_REACT_NATIVE = _words(r"react native")  # mobile, so tech-entry unless plain React is also named

# Any technical role. Matched on the title (and tags).
_TECH = _words(
    r"engineers?", r"engineering", r"developers?", r"dev", r"programmers?", r"programming", r"software",
    r"coder", r"coding", r"code reviewer", r"sre", r"devops", r"devsecops", r"mlops", r"sysadmin",
    r"system administrator", r"systems administrator", r"it (?:support|specialist|technician|administrator|analyst|engineer|operations|helpdesk)",
    r"help ?desk", r"service desk", r"desktop support", r"technical", r"tech", r"qa", r"quality assurance",
    r"sdet", r"testers?", r"test analyst", r"data (?:analyst|engineer|scientist|architect)", r"analytics engineer",
    r"bi (?:developer|analyst)", r"machine learning", r"ml", r"ai", r"llm", r"nlp", r"computer vision",
    r"architect", r"cloud", r"cyber ?security", r"security (?:analyst|engineer)", r"infosec", r"network",
    r"devrel", r"developer (?:advocate|relations)", r"web", r"web3", r"blockchain", r"solidity",
    r"smart contracts?", r"backend", r"back[- ]end", r"mobile", r"ios", r"android", r"flutter",
    r"wordpress", r"shopify", r"implementation", r"solutions? (?:engineer|consultant|architect)",
    r"prompt", r"database", r"dba", r"platform", r"infrastructure", r"embedded", r"firmware",
    r"unity", r"python", r"golang", r"go (?:developer|engineer|backend)", r"java", r"php", r"laravel",
    r"ruby", r"rails", r"django", r"\.net", r"c#", r"c\+\+", r"rust", r"scala", r"kotlin", r"swift",
    r"elixir", r"sql", r"aws", r"azure", r"gcp", r"kubernetes", r"linux", r"vue", r"angular", r"svelte",
    r"api", r"member of technical staff", r"servicenow", r"intune", r"endpoint", r"active directory",
    r"power bi", r"tableau", r"open source", r"scripting", r"product support", r"technology",
)

# Clearly non-technical titles. Dropped even when a weak tech word appears
# ("AI Sales Lead", "Technical Recruiter") unless a rescue word is also there.
_NON_TECH = _words(
    r"sales", r"account executive", r"account manager", r"ae", r"sdr", r"bdr", r"business development",
    r"marketing", r"marketer", r"growth marketer", r"seo", r"social media", r"brand", r"pr",
    r"communications", r"copywriter", r"content (?:writer|creator|reviewer|strategist|manager|marketing|moderator)",
    r"writer", r"editor", r"journalist", r"recruiter", r"recruiting", r"recruitment", r"talent (?:acquisition|partner|sourcer|manager)", r"sourcer",
    r"hr", r"human resources", r"people (?:ops|operations|partner)", r"payroll", r"accountant", r"accounting",
    r"bookkeeper", r"bookkeeping", r"controller", r"tax", r"finance", r"financial", r"legal", r"counsel",
    r"lawyer", r"attorney", r"paralegal", r"compliance", r"customer service", r"customer success",
    r"customer support", r"customer experience", r"call center", r"receptionist", r"(?:executive|virtual|office|administrative|personal) assistant",
    r"assistant", r"office manager", r"designer", r"illustrator", r"artist", r"animator", r"video",
    r"photographer", r"ux researcher", r"instructional design(?:er)?", r"teacher", r"tutor", r"instructor",
    r"translator", r"transcription", r"data entry", r"nurse", r"physician", r"therapist", r"clinical",
    r"medical", r"insurance", r"underwriter", r"real estate", r"mortgage", r"procurement", r"logistics",
    r"supply chain", r"events?", r"community (?:manager|lead|specialist|moderator)", r"partnerships?", r"fundraising", r"operations", r"coordinator",
    r"phd", r"gtm", r"go-to-market", r"language alignment", r"speakers?", r"linguists?",
)
# Words that make a title technical even next to a non-tech word.
_RESCUE = _words(
    r"engineers?", r"developers?", r"programmers?", r"technical writer", r"technical support",
    r"it (?:support|operations|specialist|technician|administrator|analyst|helpdesk)", r"data analyst",
    r"data scientist", r"sysadmin", r"system administrator", r"systems administrator", r"qa", r"sre", r"devops",
)
# Engineering outside software: a different profession, not a role to learn on.
_OTHER_ENGINEERING = _words(
    r"mechanical", r"civil", r"structural", r"electrical", r"chemical", r"mep", r"hvac", r"metrology",
    r"manufacturing", r"petroleum", r"mining", r"geotechnical", r"biomedical", r"industrial", r"aerospace",
    r"cnc", r"plumbing", r"process engineer", r"surveyor", r"estimator", r"construction",
    r"robotics", r"thermal", r"cfd", r"mbse", r"sysml", r"hardware",
)
_PHD = _words(r"ph\.?d\.?")
_RESEARCH = _words(r"research scientist", r"researcher", r"research engineer")


# HN posts that list several roles at once: judge them from the post text.
_MULTI_ROLE = re.compile(r"^\W*(?:multiple|various|several|many|all)\b.*\b(?:positions|roles|openings)\b", re.IGNORECASE)


def _tech_alternative(title: str) -> bool:
    """A multi-role title ("engineering, GTM, product, sales") with at least one tech role."""
    parts = [p for p in _ALTERNATIVES.split(title) if p.strip()]
    return len(parts) > 1 and any(
        (_ROLE_NOUN.search(p) or _ENGINEERING.search(p)) and not _NON_TECH.search(p) for p in parts
    )


def _category(job: Job) -> Category | None:
    """The digest section for a technical job, or None for a non-tech one."""
    title = job.title.strip()
    if _MULTI_ROLE.match(title):
        title = NO_ROLE
    tags = " ".join(job.tags)
    if title and title != NO_ROLE:
        automation_title = _AUTOMATION_TITLE.search(title) and not (
            _QA_AUTOMATION.search(title) or (_QA_TITLE.search(title) and not _AUTOMATION.search(title))
        )
        if _NON_TECH.search(title) and not _RESCUE.search(title) and not automation_title and not _tech_alternative(title):
            return None
        if _OTHER_ENGINEERING.search(title) and not _words(r"software", r"firmware", r"embedded").search(title):
            return None
        if _RESEARCH.search(title) and (_PHD.search(title) or _PHD.search(job.description[:3000])):
            return None  # research roles that need a PhD
        # The title decides: source tags are too noisy (a real-estate assistant tagged "sys admin").
        if not (automation_title or _TECH.search(title) or _STACK.search(title)):
            return None
        if automation_title:
            return Category.AUTOMATION
        if _STACK.search(_REACT_NATIVE.sub(" ", title)):
            return Category.STACK
    else:
        # HN posts with no recognizable role: judge from the post text.
        head = job.description[:1500]
        if not (_TECH.search(head) or _STACK.search(head)):
            return None
    if _AUTOMATION.search(tags) and not _QA_AUTOMATION.search(tags):
        return Category.AUTOMATION
    if _STACK.search(_REACT_NATIVE.sub(" ", tags)):
        return Category.STACK
    text = job.description
    if _AUTOMATION_TOOLS.search(text):
        return Category.AUTOMATION
    if len({m.group(0).lower().replace(".", "") for m in _STACK_DESCRIPTION.finditer(_REACT_NATIVE.sub(" ", text))}) >= 2:
        return Category.STACK
    return Category.TECH_ENTRY


# --- Seniority ------------------------------------------------------------------------

_TOO_SENIOR = _words(
    r"staff", r"principal", r"director", r"head of", r"head", r"vp", r"svp", r"evp", r"vice president",
    r"chief", r"cto", r"cio", r"ciso", r"cpo", r"ceo", r"coo", r"cfo", r"managers?",
)
_NOT_SENIORITY = _words(r"member of technical staff", r"mts")  # a common IC title, not staff level


_LEVEL = re.compile(r"\W*(?:senior|sr\.?|junior|jr\.?|mid(?:-level)?|intermediate|associate|entry(?:-level)?)\W*", re.IGNORECASE)
_ROLE_NOUN = _words(
    r"engineers?", r"developers?", r"scientists?", r"sres?", r"fdes?", r"designers?", r"analysts?",
    r"architects?", r"programmers?", r"devops",
)


def _too_senior(title: str) -> bool:
    """Staff+ or manager title. A title offering alternatives ("Senior/Staff Engineer",
    "Frontend Engineer, Ads Campaign Manager") passes if one alternative is a plain role."""
    title = _NOT_SENIORITY.sub(" ", title)
    if not _TOO_SENIOR.search(title):
        return False
    parts = [p for p in _ALTERNATIVES.split(title) if p.strip()]
    if len(parts) > 1:
        for part in parts:
            if not _TOO_SENIOR.search(part) and (_LEVEL.fullmatch(part) or _ROLE_NOUN.search(part)):
                return False
    return True


# --- Location -------------------------------------------------------------------------

_PAKISTAN = _words(r"pakistan", r"lahore", r"karachi", r"islamabad", r"rawalpindi", r"pkt")
_WORLDWIDE = _words(
    r"worldwide", r"world ?wide", r"world", r"anywhere", r"global", r"globally", r"international",
    r"any (?:location|country|timezone|time zone)", r"all (?:locations|countries|timezones)",
)
_ASIA = _words(r"asia", r"apac", r"asia[- ]pacific", r"south asia", r"middle east", r"mena", r"gcc")
_EMEA = _words(r"emea")
_TZ_OFFSET = re.compile(r"(?<![a-z])(?:utc|gmt)\s*(?:([+\-−–])\s*(\d{1,2})(?:[:.](\d{2}))?)?(?![a-z])", re.IGNORECASE)
_BARE_REMOTE = re.compile(
    r"^(?:\W|remote|fully|full|100%|first|friendly|only|work from home|wfh|distributed|ok|okay|possible|position|job)*$",
    re.IGNORECASE,
)
UTC_PLUS_PK = 5.0


def _offsets(text: str) -> list[float]:
    out = []
    for sign, hours, minutes in _TZ_OFFSET.findall(text):
        value = int(hours or 0) + int(minutes or 0) / 60
        out.append(-value if sign and sign in "-−–" else value)
    return out


def _timezone_covers_pakistan(text: str) -> bool:
    offsets = _offsets(text)
    if len(offsets) >= 2:
        return min(offsets) <= UTC_PLUS_PK <= max(offsets)
    return len(offsets) == 1 and abs(offsets[0] - UTC_PLUS_PK) <= 1


# A region lock written into the title: "QA Engineer - Europe", "(LATAM)", "(U.S. Based)".
_TITLE_REGION = _words(
    r"us", r"u\.s\.?", r"usa", r"united states", r"america", r"americas", r"north america", r"south america",
    r"uk", r"united kingdom", r"europe", r"eu", r"european", r"latam", r"latin america", r"canada",
    r"india", r"brazil", r"mexico", r"germany", r"bulgaria", r"poland", r"spain", r"france", r"portugal",
    r"romania", r"australia", r"philippines", r"argentina", r"colombia", r"nigeria", r"kenya",
    r"south africa", r"cet", r"est", r"pst",
)
_NON_PREFIX = re.compile(r"(?<![a-z0-9])non-?\s*[a-z.]+", re.IGNORECASE)  # "Non-US/Non-EU Position" is open to us


def title_region_lock(title: str) -> bool:
    title = _NON_PREFIX.sub(" ", title)
    if not _TITLE_REGION.search(title):
        return False
    return not (_PAKISTAN.search(title) or _WORLDWIDE.search(title) or _ASIA.search(title) or _EMEA.search(title))


def location_rule(job: Job) -> str | None:
    """Why the location passes ("worldwide", "asia", ...), or None when the job is region-locked."""
    if job.location_restrictions:
        names = {r.strip().lower() for r in job.location_restrictions}
        return "pakistan" if "pakistan" in names else None
    text = job.location.strip()
    if not text:
        return "unspecified"
    if _PAKISTAN.search(text):
        return "pakistan"
    if _WORLDWIDE.search(text):
        return "worldwide"
    if _ASIA.search(text):
        return "asia"
    if _EMEA.search(text):
        return "emea"
    if _timezone_covers_pakistan(text):
        return "timezone"
    if _BARE_REMOTE.match(text):
        return "unspecified"
    return None


# --- Work authorization ---------------------------------------------------------------

_COUNTRY = (
    r"(?:the )?(?:us|u\.s\.?a?\.?|usa|united states(?: of america)?|america|uk|u\.k\.|united kingdom|"
    r"canada|eu|european union|europe|australia|new zealand|germany|france|netherlands|ireland|spain|"
    r"india|brazil|mexico|israel|japan|singapore|switzerland)"
)
_WORK_AUTH = re.compile(
    "|".join(
        [
            rf"(?:authori[sz]ed|eligible|permitted|right|legally able) to (?:live and )?work (?:in|within) {_COUNTRY}(?![a-z])",
            rf"(?:work|employment) (?:authori[sz]ation|eligibility|permit) (?:in|for) {_COUNTRY}(?![a-z])",
            r"(?<![a-z])(?:us|u\.s\.|american|canadian|uk|british) citizens?(?:hip)?(?![a-z])",
            r"(?<![a-z])(?:security|secret|government|federal|public trust|top secret|ts/sci) clearance",
            r"(?<![a-z])clearance (?:is )?required",
            r"(?<![a-z])ts/sci(?![a-z])",
            r"(?<![a-z])w-?2(?![a-z0-9])",
            r"(?<![a-z])green card",
            rf"must (?:currently )?(?:reside|live|be located|be based|be residing|be a resident) (?:in|within) {_COUNTRY}(?![a-z])",
            # "US-based only" locks the job; "benefits for US-based employees" does not.
            r"(?<![a-z])(?:us|u\.s\.)[- ]based (?:(?:candidates?|applicants?|residents?|individuals?|talent|professionals?) )?only",
            r"must be (?:us|u\.s\.)[- ]based",
            rf"(?:candidates?|applicants?|residents?) (?:must be |who are )?(?:located|based|residing) in {_COUNTRY} only",
            rf"{_COUNTRY} residents only",
            rf"(?:only|exclusively) (?:open|available|accepting applications?) (?:to|from) (?:candidates?|applicants?|residents?|people)? ?(?:located |based |residing )?(?:in|of) {_COUNTRY}(?![a-z])",
        ]
    ),
    re.IGNORECASE,
)


def work_authorization_lock(text: str) -> bool:
    """True when the text restricts the job to people already allowed to work in one country."""
    return bool(_WORK_AUTH.search(text))


# --- Years of experience --------------------------------------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUM = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
_YEARS = re.compile(
    rf"(?<![\w.]){_NUM}\s*(\+|plus)?\s*(?:(?:-|–|to)\s*{_NUM}\s*\+?\s*)?(?:years?|yrs?)\b(\s+(?:of\s+)?(?:[\w/+#.-]+\s+){{0,3}}?(?:experience|exp)\b)?",
    re.IGNORECASE,
)
_YEARS_LEAD = re.compile(rf"(?:at least|minimum(?: of)?|min\.?|over|more than)\s+{_NUM}\s+(?:years?|yrs?)\b", re.IGNORECASE)


def _to_int(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBER_WORDS[token.lower()]


def required_years(text: str) -> int | None:
    """Years of experience the posting asks for (the largest stated minimum), or None.

    Counts "5+ years", "3-5 years", "at least 4 years" and "2 years of experience";
    ignores stray numbers like "founded 10 years ago".
    """
    found: list[int] = []
    for m in _YEARS.finditer(text):
        low, plus, high, experience = m.group(1), m.group(2), m.group(3), m.group(4)
        if plus or high or experience:
            found.append(_to_int(low))
    for m in _YEARS_LEAD.finditer(text):
        found.append(_to_int(m.group(1)))
    found = [n for n in found if n <= 20]
    return max(found) if found else None


# --- The stage ------------------------------------------------------------------------


def evaluate(job: Job) -> Verdict:
    """Return keep/drop for one job, with its category and location rule.

    - keep=True  -> category is set, location_rule says why location passed
                    ("worldwide", "asia", "emea", "pakistan", "timezone", "unspecified").
    - keep=False -> reason is one of DROP_LABELS.
    """
    category = _category(job)
    if category is None:
        return Verdict.drop(NON_TECH)
    if _too_senior(job.title):
        return Verdict.drop(SENIORITY)
    rule = location_rule(job)
    if rule is None or (rule != "pakistan" and title_region_lock(job.title)):
        return Verdict.drop(LOCATION)
    if job.source == "hn" and rule == "unspecified":
        # HN posts that only say "REMOTE" are nearly always US-remote (PLAN.md section 2).
        return Verdict.drop(LOCATION)
    if rule != "pakistan" and work_authorization_lock(f"{job.title}\n{job.location}\n{job.description}"):
        return Verdict.drop(WORK_AUTHORIZATION)
    return Verdict(keep=True, category=category, location_rule=rule)
