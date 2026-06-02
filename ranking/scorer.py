import re

from config.keywords import (
    POSITIVE_KEYWORDS,
    NEGATIVE_KEYWORDS,
    ROLE_BONUSES,
    ROLE_PENALTIES,
)


def calculate_score(title, description=""):

    title_text = title.lower()

    description_text = description.lower()

    score = 0
    matched = []

    for keyword, points in POSITIVE_KEYWORDS.items():

        if keyword in title_text:
            score += points * 3
            matched.append(keyword)

        elif keyword in description_text:
            score += points
            matched.append(keyword)

    for role, points in ROLE_BONUSES.items():

        if role in title_text:
            score += points

    for role, points in ROLE_PENALTIES.items():

        if role in title_text:
            score += points

        # Experience-aware title adjustments

    seniority_penalties = {
        "senior staff": -60,
        "staff": -80,
        "principal": -100,
        "director": -120,
        "head of": -120,
        "vp": -150,
        "vice president": -150,
        "engineering manager": -100,
        "manager": -50,
    }

    junior_bonuses = {
        "intern": 40,
        "new grad": 35,
        "graduate": 30,
        "entry level": 30,
        "junior": 25,
        "associate": 20,
        "early career": 35,
    }

    for term, points in seniority_penalties.items():
        if term in title_text:
            score += points

    for term, points in junior_bonuses.items():
        if term in title_text:
            score += points


    years_matches = re.findall(
        r"(\d+)\+?\s*(?:years|year|yrs|yr)",
        description_text,
    )

    if years_matches:

        max_years = max(int(years) for years in years_matches)

        if max_years >= 10:
            score -= 80

        elif max_years >= 8:
            score -= 60

        elif max_years >= 7:
            score -= 40

        elif max_years >= 6:
            score -= 20

    for keyword, points in NEGATIVE_KEYWORDS.items():

        if keyword in title_text:
            score += points

    return score, matched