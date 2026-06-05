from pathlib import Path
import json
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    if len(sys.argv) != 2:
        print(
            "Usage:\n"
            "python -m experiments.eval.consistency_check "
            "<run.json>"
        )
        sys.exit(1)

    run_path = Path(sys.argv[1])

    run_data = load_json(run_path)

    base_dir = Path(__file__).resolve().parent.parent

    resume_text = (
        base_dir
        / "samples"
        / "resume.txt"
    ).read_text(
        encoding="utf-8"
    ).lower()

    print("=" * 60)
    print("CONSISTENCY CHECK")
    print()

    for job_name, assessment in run_data["jobs"].items():

        strengths = {
            item.strip().lower()
            for item in assessment["strengths"]
        }

        missing = {
            item.strip().lower()
            for item in assessment["missing_skills"]
        }

        overlap = strengths & missing

        if overlap:
            print(job_name)
            print("  CONTRADICTION")

            for item in sorted(overlap):
                print(f"    {item}")

            print()

        for skill in missing:
            if skill in resume_text:
                print(job_name)
                print(
                    "  MISSING SKILL FOUND "
                    "IN RESUME"
                )
                print(f"    {skill}")
                print()

        for strength in strengths:
            if strength not in resume_text:
                print(job_name)
                print(
                    "  WARNING: STRENGTH "
                    "NOT FOUND IN RESUME"
                )
                print(f"    {strength}")
                print()


if __name__ == "__main__":
    main()