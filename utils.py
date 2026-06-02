from config.keywords import (
    PRIMARY_KEYWORDS,
    SECONDARY_KEYWORDS
)


def is_relevant(text):

    text = text.lower()

    for keyword in PRIMARY_KEYWORDS:

        if keyword in text:
            return True

    for keyword in SECONDARY_KEYWORDS:

        if keyword in text:
            return True

    return False