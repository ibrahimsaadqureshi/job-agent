import requests

from greenhouse.companies import COMPANIES


def get_greenhouse_jobs():

    all_jobs = []

    for company in COMPANIES:

        url = (
            f"https://boards-api.greenhouse.io/"
            f"v1/boards/{company}/jobs"
        )

        try:

            response = requests.get(url)

            data = response.json()

            if "jobs" not in data:

                print(
                    f"Skipping {company}"
                )

                continue

            jobs = data["jobs"]

            print(
                f"{company}: "
                f"{len(jobs)} jobs"
            )

            for job in jobs:

                all_jobs.append({

                    "title": job.get(
                        "title",
                        ""
                    ),

                    "company": company,

                    "location": (
                        job.get(
                            "location",
                            {}
                        ).get(
                            "name",
                            "Unknown"
                        )
                    ),

                    "url": job.get(
                        "absolute_url",
                        ""
                    ),

                    "source": "greenhouse",

                    "description": ""

                })

        except Exception as e:

            print(
                f"Failed: {company}"
            )

            print(e)

            continue

    print(
        f"Greenhouse: "
        f"{len(all_jobs)} jobs"
    )

    return all_jobs