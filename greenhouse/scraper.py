import requests

from bs4 import BeautifulSoup

from greenhouse.companies import COMPANIES

from html import unescape

def clean_description(html):

    if not html:

        return ""

    html = unescape(html)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    return "\n".join(lines)


def get_greenhouse_jobs():

    all_jobs = []

    for company in COMPANIES:

        url = (
            f"https://boards-api.greenhouse.io/"
            f"v1/boards/{company}/jobs"
            f"?content=true"
        )

        try:

            response = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0"
                },
                timeout=15
            )

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

                description = (
                    clean_description(
                        job.get(
                            "content",
                            ""
                        )
                    )
                )

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

                    "description": description

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