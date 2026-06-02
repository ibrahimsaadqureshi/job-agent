import requests

company = input(
    "Company: "
)

url = (
    f"https://boards-api.greenhouse.io/"
    f"v1/boards/{company}/jobs"
)

response = requests.get(url)

print(
    "Status:",
    response.status_code
)

data = response.json()

print(
    data.keys()
)