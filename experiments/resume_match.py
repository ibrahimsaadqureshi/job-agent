from pathlib import Path
import json

from assessment_utils import generate_assessment


BASE_DIR = Path(__file__).parent

resume_path = BASE_DIR / "samples" / "resume.txt"
job_path = BASE_DIR / "samples" / "jobs" / "job1.txt"
prompt_path = BASE_DIR / "prompts" / "resume_match_prompt_v2.txt"

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

last_error = None
successful_attempt = None

for attempt in range(2):
    try:
        result = generate_assessment(full_prompt)
        successful_attempt = attempt + 1
        break

    except Exception as e:
        last_error = e
        print(f"Attempt {attempt + 1} failed: {e}")

else:
    raise RuntimeError(
        f"Assessment generation failed after 2 attempts: {last_error}"
    )

assessment_path = BASE_DIR / "assessment.json"

assessment_path.write_text(
    json.dumps(result, indent=2),
    encoding="utf-8",
)

print(
    f"Assessment generated successfully on attempt "
    f"{successful_attempt}"
)

print()

print(json.dumps(result, indent=2))