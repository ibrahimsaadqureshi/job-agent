PRIMARY_KEYWORDS = [
    "ai",
    "automation",
    "workflow",
    "python",
    "crm",
    "n8n",
    "zapier",
    "make",
    "gohighlevel",
    "highlevel",
]

SECONDARY_KEYWORDS = [
    "virtual assistant",
    "executive assistant",
    "administrative assistant",
    "operations",
    "analyst",
    "implementation",
    "customer success",
    "solutions",
    "support",
]
POSITIVE_KEYWORDS = {
    "automation": 15,
    "ai": 10,
    "openai": 15,
    "n8n": 25,
    "zapier": 20,
    "make": 20,
    "workflow": 15,
    "crm": 15,
    "api": 10,
    "integration": 10,
    "python": 10,
}

NEGATIVE_KEYWORDS = {
    "senior": -20,
    "staff": -30,
    "principal": -35,
    "director": -40,
    "lead": -15,
}

ROLE_BONUSES = {
    "ai engineer": 80,
    "ml engineer": 80,
    "machine learning engineer": 80,
    "founding ai engineer": 100,
    "integrations engineer": 70,
    "automation": 50,
    "workflow": 50,
    "genai": 40,
    "enterprise ai": 40,
    "openai": 40,
}

ROLE_PENALTIES = {
    "executive assistant": -60,
    "administrative assistant": -60,
    "bookkeeper": -60,
    "cleaner": -100,
    "human resources": -50,
    "hr": -50,
    "communications": -30,
}