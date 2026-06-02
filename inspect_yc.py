import requests
from bs4 import BeautifulSoup

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

for link in soup.find_all("a")[:50]:

    text = link.get_text(
        strip=True
    )

    href = link.get("href")

    print(text)
    print(href)
    print("-" * 50)