import requests
from bs4 import BeautifulSoup


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

        # Only actual job links
        if "/companies/" not in href:
            continue

        if "/jobs/" not in href:
            continue

        text = link.get_text(strip=True)

        if not text:
            continue

        try:
            parts = href.split("/")
            company = parts[2]
        except Exception:
            company = "unknown"

        job = {
            "title": text,
            "company": company,
            "location": "Unknown",
            "url": f"https://www.ycombinator.com{href}",
            "source": "yc",
            "description": ""
        }

        jobs.append(job)
    print(
        f"YC: {len(jobs)} jobs"
    )

    return jobs