import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

DOCS_VERSION = "0.150.0"
TARGET = 350
OUT = Path(__file__).resolve().parent.parent / "evals" / "questions.json"
DOCS_LINK = re.compile(r"https?://fastapi\.tiangolo\.com[^\s)\]>\"']*")

QUERY = """
query($cursor: String) {
  repository(owner: "fastapi", name: "fastapi") {
    discussions(first: 50, after: $cursor, answered: true,
                orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url createdAt body
        category { name }
        answer { url body }
      }
    }
  }
}
"""


def fetch_page(token, cursor):
    payload = json.dumps({"query": QUERY, "variables": {"cursor": cursor}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        sys.exit(f"GitHub error: {data['errors']}")
    return data["data"]["repository"]["discussions"]


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set.")

    if OUT.exists():
        data = json.loads(OUT.read_text(encoding="utf-8"))
    else:
        data = {"collected_on": date.today().isoformat(), "docs_version": DOCS_VERSION, "questions": []}
    questions = data["questions"]
    seen = {q["id"] for q in questions}
    cursor = None
    while len(questions) < TARGET:
        page = fetch_page(token, cursor)
        for d in page["nodes"]:
            if d["category"]["name"] != "Questions" or d["number"] in seen:
                continue
            if d["createdAt"] >= data["collected_on"] or len(questions) >= TARGET:
                continue
            seen.add(d["number"])
            questions.append(
                {
                    "id": d["number"],
                    "url": d["url"],
                    "created_at": d["createdAt"],
                    "title": d["title"],
                    "question": d["body"],
                    "answer_url": d["answer"]["url"],
                    "answer": d["answer"]["body"],
                    "docs_links": sorted(set(DOCS_LINK.findall(d["answer"]["body"]))),
                    "tag": "",
                }
            )
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    linked = sum(1 for q in questions if q["docs_links"])
    print(f"Saved {len(questions)} questions to {OUT}")
    print(f"{linked} of them have an answer that links to fastapi.tiangolo.com")


if __name__ == "__main__":
    main()
