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

    for keyword, points in NEGATIVE_KEYWORDS.items():

        if keyword in title_text:
            score += points

    return score, matched