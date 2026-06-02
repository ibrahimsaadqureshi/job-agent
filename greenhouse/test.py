import requests

url = "https://boards-api.greenhouse.io/v1/boards/scaleai/jobs"

response = requests.get(url)

print("Status:", response.status_code)

data = response.json()

print("Keys:", data.keys())

print("Jobs:", len(data["jobs"]))

print()

for job in data["jobs"][:5]:
    print(job["title"])