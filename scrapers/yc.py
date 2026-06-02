import requests

from bs4 import BeautifulSoup


def get_job_description(url):

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=10
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        meta = soup.find(
            "meta",
            attrs={
                "name": "description"
            }
        )

        if not meta:

            return ""

        description = meta.get(
            "content",
            ""
        )

        description = " ".join(
            description.split()
        )

        return description

    except Exception as e:

        print(
            f"Failed description: {url}"
        )

        print(e)

        return ""


def get_yc_jobs():

    url = "https://www.ycombinator.com/jobs"

    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    jobs = []

    links = soup.find_all("a")

    for link in links:

        href = link.get("href")

        if not href:
            continue

        if "/companies/" not in href:
            continue

        if "/jobs/" not in href:
            continue

        text = link.get_text(
            strip=True
        )

        if not text:
            continue

        try:

            parts = href.split("/")

            company = parts[2]

        except Exception:

            company = "unknown"

        job_url = (
            f"https://www.ycombinator.com"
            f"{href}"
        )

        description = (
            get_job_description(
                job_url
            )
        )

        job = {

            "title": text,

            "company": company,

            "location": "Unknown",

            "url": job_url,

            "source": "yc",

            "description": description

        }

        jobs.append(job)

    print(
        f"YC: {len(jobs)} jobs"
    )

    return jobs