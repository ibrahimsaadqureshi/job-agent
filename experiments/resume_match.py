from pathlib import Path
import requests


BASE_DIR = Path(__file__).parent

resume_path = BASE_DIR / "samples" / "resume.txt"
job_path = BASE_DIR / "samples" / "job_description.txt"
prompt_path = BASE_DIR / "prompts" / "resume_match_prompt.txt"

resume_text = resume_path.read_text(encoding="utf-8")
job_text = job_path.read_text(encoding="utf-8")
prompt_text = prompt_path.read_text(encoding="utf-8")

full_prompt = f"""
{prompt_text}

RESUME:

{resume_text}

JOB DESCRIPTION:

{job_text}
"""

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

import json

raw_response = data["response"]

clean_response = raw_response.replace("```json", "")
clean_response = clean_response.replace("```", "")
clean_response = clean_response.strip()

result = json.loads(clean_response)

print(json.dumps(result, indent=2))