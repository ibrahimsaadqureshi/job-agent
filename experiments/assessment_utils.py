import json
import requests


def validate_assessment(result):
    required_keys = {
        "match_score",
        "strengths",
        "missing_skills",
        "summary",
        "talking_points",
    }

    missing_keys = required_keys - result.keys()

    if missing_keys:
        raise ValueError(
            f"Missing required JSON fields: {sorted(missing_keys)}"
        )

    if not isinstance(result["match_score"], int):
        raise ValueError("match_score must be an integer")

    if not isinstance(result["strengths"], list):
        raise ValueError("strengths must be a list")

    if not isinstance(result["missing_skills"], list):
        raise ValueError("missing_skills must be a list")

    if not isinstance(result["summary"], str):
        raise ValueError("summary must be a string")

    if not isinstance(result["talking_points"], list):
        raise ValueError("talking_points must be a list")

    if not 0 <= result["match_score"] <= 100:
        raise ValueError(
            f"match_score out of range: {result['match_score']}"
        )


def generate_assessment(full_prompt):
    response = requests.post(
        "http://127.0.0.1:11434/api/generate",
        json={
            "model": "qwen2.5:7b",
            "prompt": full_prompt,
            "stream": False,
        },
        timeout=300,
    )

    response.raise_for_status()

    data = response.json()

    raw_response = data["response"]

    clean_response = raw_response.replace("```json", "")
    clean_response = clean_response.replace("```", "")
    clean_response = clean_response.strip()

    result = json.loads(clean_response)

    validate_assessment(result)

    return result