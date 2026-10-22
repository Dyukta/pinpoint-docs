import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "evals" / "questions.json"
DOCS = ROOT / "data" / "fastapi-0.150.0" / "docs" / "en" / "docs"
TAGS = {"d": "docs", "o": "other-library", "b": "bug", "s": "skip"}
SHOW = 2000
PAGES = {p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md")}


def link_to_page(url):
    path = url.split("fastapi.tiangolo.com", 1)[1].split("#")[0].split("?")[0].strip("/")
    for candidate in (f"{path}.md", f"{path}/index.md", "index.md" if not path else None):
        if candidate in PAGES:
            return candidate
    return None


def ask_pages(q):
    suggested = sorted({p for p in map(link_to_page, q["docs_links"]) if p})
    hint = f"Enter = {', '.join(suggested)}, 'back' = change tag" if suggested else "Enter = change tag"
    while True:
        raw = input(f"Docs page(s), comma separated [{hint}]: ").strip()
        if raw == "back" or (not raw and not suggested):
            return None
        entries = [p.strip() for p in raw.split(",") if p.strip()]
        pages = [link_to_page(p) or p if "fastapi.tiangolo.com" in p else p for p in entries] if raw else suggested
        missing = [p for p in pages if p not in PAGES]
        if not missing:
            return pages
        print(f"Not found in {DOCS}: {missing}")


def main():
    data = json.loads(FILE.read_text(encoding="utf-8"))
    questions = data["questions"]
    review = "--review" in sys.argv or "--split" in sys.argv
    if "--split" in sys.argv:
        name = sys.argv[sys.argv.index("--split") + 1]
        ids = set(json.loads((ROOT / "evals" / "split.json").read_text(encoding="utf-8"))[name])
        todo = [q for q in questions if q["id"] in ids and q.get("tagged_by") not in ("human", "human-reviewed")]
        todo.sort(key=lambda q: q["tag"] != "docs")
    elif review:
        todo = [
            q
            for q in questions
            if q.get("tagged_by") == "draft" and (q["tag"] == "docs" or "borderline" in q.get("why", "").lower())
        ]
    else:
        todo = [q for q in questions if not q["tag"]]
    for n, q in enumerate(todo, 1):
        print("\n" + "=" * 80)
        print(f"[{n}/{len(todo)}] #{q['id']}  {q['title']}\n{q['url']}\n")
        print("QUESTION:\n" + q["question"][:SHOW])
        print("\nACCEPTED ANSWER:\n" + q["answer"][:SHOW])
        print(f"\nDocs links: {q['docs_links'] or 'none'}")
        if review:
            print(f"\nDRAFT: {q['tag']} {q['gold_pages']}\nWHY: {q['why']}")
        pages = None
        while pages is None:
            prompt = "Enter=keep draft  " if review else ""
            key = input(f"\n{prompt}d=docs  o=other-library  b=bug  s=skip  q=quit: ").strip().lower()
            if review and key == "":
                key = next(k for k, t in TAGS.items() if t == q["tag"])
                pages = q["gold_pages"]
            elif key in ("o", "b", "s"):
                pages = []
            elif key == "d":
                pages = ask_pages(q)
            elif key == "q":
                break
        if key == "q":
            break
        q["tag"] = TAGS[key]
        q["gold_pages"] = pages
        q["tagged_by"] = "human-reviewed" if review else "human"
        FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = {t: sum(q["tag"] == t for q in questions) for t in TAGS.values()}
    print(f"\nTagged so far: {counts}, untagged: {sum(not q['tag'] for q in questions)}")


if __name__ == "__main__":
    main()
