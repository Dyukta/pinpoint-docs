import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "evals" / "questions.json"
DOCS = ROOT / "data" / "fastapi-0.150.0" / "docs" / "en" / "docs"
TAGS = {"d": "docs", "o": "other-library", "b": "bug", "s": "skip"}
SHOW = 2000


def link_to_page(url):
    path = url.split("fastapi.tiangolo.com", 1)[1].split("#")[0].split("?")[0].strip("/")
    for candidate in (f"{path}.md", f"{path}/index.md", "index.md" if not path else None):
        if candidate and (DOCS / candidate).is_file():
            return candidate
    return None


def ask_pages(q):
    suggested = sorted({p for p in map(link_to_page, q["docs_links"]) if p})
    hint = f" [Enter = {', '.join(suggested)}]" if suggested else ""
    while True:
        raw = input(f"Docs page(s), comma separated{hint}: ").strip()
        entries = [p.strip() for p in raw.split(",") if p.strip()]
        pages = [link_to_page(p) or p if "fastapi.tiangolo.com" in p else p for p in entries] if raw else suggested
        missing = [p for p in pages if not (DOCS / p).is_file()]
        if pages and not missing:
            return pages
        print(f"Not found in {DOCS}: {missing or 'nothing entered'}")


def main():
    data = json.loads(FILE.read_text(encoding="utf-8"))
    questions = data["questions"]
    todo = [q for q in questions if not q["tag"]]
    for n, q in enumerate(todo, 1):
        print("\n" + "=" * 80)
        print(f"[{n}/{len(todo)}] #{q['id']}  {q['title']}\n{q['url']}\n")
        print("QUESTION:\n" + q["question"][:SHOW])
        print("\nACCEPTED ANSWER:\n" + q["answer"][:SHOW])
        print(f"\nDocs links: {q['docs_links'] or 'none'}")
        key = ""
        while key not in TAGS and key != "q":
            key = input("\nd=docs  o=other-library  b=bug  s=skip  q=quit: ").strip().lower()
        if key == "q":
            break
        q["tag"] = TAGS[key]
        q["gold_pages"] = ask_pages(q) if key == "d" else []
        FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = {t: sum(q["tag"] == t for q in questions) for t in TAGS.values()}
    print(f"\nTagged so far: {counts}, untagged: {sum(not q['tag'] for q in questions)}")


if __name__ == "__main__":
    main()
