from pathlib import Path
import json

from assessment_utils import generate_assessment


BASE_DIR = Path(__file__).parent

resume_path = BASE_DIR / "samples" / "resume.txt"
jobs_dir = BASE_DIR / "samples" / "jobs"
assessments_dir = BASE_DIR / "assessments"
prompt_path = BASE_DIR / "prompts" / "resume_match_prompt.txt"

resume_text = resume_path.read_text(encoding="utf-8")
prompt_text = prompt_path.read_text(encoding="utf-8")

job_files = sorted(jobs_dir.glob("*.txt"))

print(f"Resume loaded: {resume_path.name}")
print()

print(f"Found {len(job_files)} job(s)")
print()

results = []

for job_file in job_files:
    print("=" * 60)
    print(f"Evaluating {job_file.name}")
    print()

    job_text = job_file.read_text(encoding="utf-8")

    full_prompt = f"""
{prompt_text}

RESUME:

{resume_text}

JOB DESCRIPTION:

{job_text}
"""

    last_error = None

    for attempt in range(2):
        try:
            result = generate_assessment(full_prompt)

            print(
                f"Assessment generated successfully "
                f"on attempt {attempt + 1}"
            )

            break

        except Exception as e:
            last_error = e

            print(
                f"Attempt {attempt + 1} failed: {e}"
            )

    else:
        print(
            f"Skipping {job_file.name}. "
            f"Assessment failed after 2 attempts."
        )

        continue

    assessment_path = (
        assessments_dir /
        f"{job_file.stem}.json"
    )

    assessment_path.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    results.append(
        {
            "job_file": job_file.name,
            "match_score": result["match_score"],
            "strengths": result["strengths"],
            "missing_skills": result["missing_skills"],
            "summary": result["summary"],
        }
    )

    print(
        f"Match Score: {result['match_score']}"
    )

    print(
        f"Saved: {assessment_path.name}"
    )

    print()

results.sort(
    key=lambda x: x["match_score"],
    reverse=True,
)

print("=" * 60)
print("TOP MATCHES")
print()

for index, result in enumerate(results, start=1):
    print(
        f"{index}. "
        f"{result['job_file']} - "
        f"{result['match_score']}"
    )

    print()

    print("Top Strengths:")
    for strength in result["strengths"][:3]:
        print(f"- {strength}")

    print()

    print("Missing Skills:")
    for skill in result["missing_skills"][:3]:
        print(f"- {skill}")

    print()

    print("Summary:")
    print(result["summary"])

    print()
    print("-" * 60)
    print()