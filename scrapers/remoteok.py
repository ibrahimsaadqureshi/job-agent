import requests

from utils import is_relevant


def get_remoteok_jobs():

    url = "https://remoteok.com/api"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers
    )

    data = response.json()

    jobs = []

    for job in data:

        if not isinstance(
            job,
            dict
        ):
            continue

        title = job.get(
            "position"
        )

        if not title:
            continue

        description = job.get(
            "description",
            ""
        )

        combined_text = (
            f"{title} {description}"
        )

        if not is_relevant(
            combined_text
        ):
            continue

        jobs.append({

            "title": title,

            "company": job.get(
                "company",
                "Unknown"
            ),

            "location": job.get(
                "location",
                "Remote"
            ),

            "url": job.get(
                "url"
            ),

            "source": "remoteok",

            "description": description

        })

    print(
        f"RemoteOK: "
        f"{len(jobs)} jobs"
    )

    return jobs