import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

DOCS_VERSION = "0.150.0"
TARGET = 150
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

    questions, cursor = [], None
    while len(questions) < TARGET:
        page = fetch_page(token, cursor)
        for d in page["nodes"]:
            if d["category"]["name"] != "Questions":
                continue
            questions.append({
                "id": d["number"],
                "url": d["url"],
                "created_at": d["createdAt"],
                "title": d["title"],
                "question": d["body"],
                "answer_url": d["answer"]["url"],
                "answer": d["answer"]["body"],
                "docs_links": sorted(set(DOCS_LINK.findall(d["answer"]["body"]))),
                "tag": "",
            })
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    questions = questions[:TARGET]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "collected_on": date.today().isoformat(),
        "docs_version": DOCS_VERSION,
        "questions": questions,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    linked = sum(1 for q in questions if q["docs_links"])
    print(f"Saved {len(questions)} questions to {OUT}")
    print(f"{linked} of them have an answer that links to fastapi.tiangolo.com")


if __name__ == "__main__":
    main()
