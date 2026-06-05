from pathlib import Path
from datetime import datetime
import json

from experiments.assessment_utils import generate_assessment


BASE_DIR = Path(__file__).resolve().parent.parent

resume_path = BASE_DIR / "samples" / "resume.txt"
jobs_dir = BASE_DIR / "samples" / "jobs"
prompt_path = BASE_DIR / "prompts" / "resume_match_prompt.txt"

eval_results_dir = (
    BASE_DIR / "eval" / "eval_results"
)

eval_results_dir.mkdir(
    parents=True,
    exist_ok=True,
)

resume_text = resume_path.read_text(
    encoding="utf-8"
)

prompt_text = prompt_path.read_text(
    encoding="utf-8"
)

job_files = sorted(
    jobs_dir.glob("*.txt")
)

results = {}

for job_file in job_files:
    print(
        f"Evaluating {job_file.name}..."
    )

    job_text = job_file.read_text(
        encoding="utf-8"
    )

    full_prompt = f"""
{prompt_text}

RESUME:

{resume_text}

JOB DESCRIPTION:

{job_text}
"""

    result = generate_assessment(
        full_prompt
    )

    results[job_file.name] = result

timestamp = datetime.utcnow().strftime(
    "%Y%m%d_%H%M%S"
)

output = {
    "timestamp": timestamp,
    "model": "qwen2.5:7b",
    "jobs": results,
}

output_file = (
    eval_results_dir /
    f"run_{timestamp}.json"
)

output_file.write_text(
    json.dumps(output, indent=2),
    encoding="utf-8",
)

print()
print(
    f"Saved evaluation run:"
)
print(output_file)