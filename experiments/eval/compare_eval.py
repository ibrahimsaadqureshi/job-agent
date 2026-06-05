from pathlib import Path
import json
import sys


def load_run(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_rankings(run_data):
    ranked = sorted(
        run_data["jobs"].items(),
        key=lambda item: item[1]["match_score"],
        reverse=True,
    )

    return {
        job_name: rank
        for rank, (job_name, _) in enumerate(
            ranked,
            start=1,
        )
    }


def print_score_drift(run_a, run_b):
    print("=" * 60)
    print("SCORE DRIFT")
    print()

    for job_name in sorted(run_a["jobs"]):
        score_a = run_a["jobs"][job_name]["match_score"]
        score_b = run_b["jobs"][job_name]["match_score"]

        delta = score_b - score_a

        print(
            f"{job_name}: "
            f"{score_a} -> {score_b} "
            f"({delta:+d})"
        )

    print()


def print_rank_changes(run_a, run_b):
    print("=" * 60)
    print("RANK CHANGES")
    print()

    ranks_a = build_rankings(run_a)
    ranks_b = build_rankings(run_b)

    for job_name in sorted(ranks_a):
        print(
            f"{job_name}: "
            f"#{ranks_a[job_name]} "
            f"-> "
            f"#{ranks_b[job_name]}"
        )

    print()


def print_skill_changes(run_a, run_b):
    print("=" * 60)
    print("SKILL CHANGES")
    print()

    for job_name in sorted(run_a["jobs"]):
        strengths_a = set(
            run_a["jobs"][job_name]["strengths"]
        )

        strengths_b = set(
            run_b["jobs"][job_name]["strengths"]
        )

        missing_a = set(
            run_a["jobs"][job_name]["missing_skills"]
        )

        missing_b = set(
            run_b["jobs"][job_name]["missing_skills"]
        )

        added_strengths = strengths_b - strengths_a
        removed_strengths = strengths_a - strengths_b

        added_missing = missing_b - missing_a
        removed_missing = missing_a - missing_b

        if (
            not added_strengths
            and not removed_strengths
            and not added_missing
            and not removed_missing
        ):
            continue

        print(job_name)

        if added_strengths:
            print("  Added strengths:")
            for item in sorted(added_strengths):
                print(f"    + {item}")

        if removed_strengths:
            print("  Removed strengths:")
            for item in sorted(removed_strengths):
                print(f"    - {item}")

        if added_missing:
            print("  Added missing skills:")
            for item in sorted(added_missing):
                print(f"    + {item}")

        if removed_missing:
            print("  Removed missing skills:")
            for item in sorted(removed_missing):
                print(f"    - {item}")

        print()


def main():
    if len(sys.argv) != 3:
        print(
            "Usage:\n"
            "python -m experiments.eval.compare_eval "
            "<run_a.json> <run_b.json>"
        )
        sys.exit(1)

    run_a_path = Path(sys.argv[1])
    run_b_path = Path(sys.argv[2])

    run_a = load_run(run_a_path)
    run_b = load_run(run_b_path)

    print_score_drift(run_a, run_b)
    print_rank_changes(run_a, run_b)
    print_skill_changes(run_a, run_b)


if __name__ == "__main__":
    main()