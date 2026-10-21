import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "fastapi-0.150.0"
INCLUDE_BASE = SRC / "docs" / "en"
DOCS = INCLUDE_BASE / "docs"
OUT = ROOT / "data" / "chunks.jsonl"
SITE = "https://fastapi.tiangolo.com/"
MAX_CHARS = 1500

INCLUDE = re.compile(r"^\{\*\s*(\S+)(.*?)\*\}\s*$")
HEADING = re.compile(r"^(#{1,3}) (.+?)(?: \{ #([\w-]+) \})?\s*$")
ADMONITION = re.compile(r"^/// ?\w*(?: \| (.*))?$")


def include_code(match):
    path = INCLUDE_BASE / match.group(1)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    ranges = re.search(r"ln\[([\d:,]+)\]", match.group(2))
    if ranges:
        picked = []
        for r in ranges.group(1).split(","):
            start, _, end = r.partition(":")
            picked += lines[int(start) - 1:int(end or start)]
        lines = picked
    lines = [l if len(l) <= 200 else l[:80] + " ..." for l in lines]
    return ["```python", *lines, "```"]


def page_url(page):
    path = page.removesuffix(".md")
    path = path.removesuffix("index")
    return SITE + (path.rstrip("/") + "/" if path else "")


def split_long(text):
    pieces, cur, cut, size, fence = [], [], 0, 0, False
    for line in text.splitlines():
        if not fence and (not line.strip() or line.startswith(("* ", "- "))):
            cut = len(cur)
        if size + len(line) > MAX_CHARS and cut:
            pieces.append("\n".join(cur[:cut]))
            cur, cut = cur[cut:], 0
            size = sum(len(l) + 1 for l in cur)
        if line.lstrip().startswith("```"):
            fence = not fence
        cur.append(line)
        size += len(line) + 1
    pieces.append("\n".join(cur))
    return [p.strip() for p in pieces if p.strip()]


def split_page(page, text):
    chunks, buf, fence = [], [], False
    title = section = page
    anchor = ""

    def flush():
        body = "\n".join(buf).strip()
        if body and not HEADING.match(body):
            for i, piece in enumerate(split_long(body)):
                chunks.append({
                    "id": f"{page}#{len(chunks)}",
                    "page": page,
                    "title": title,
                    "section": section,
                    "url": page_url(page) + (f"#{anchor}" if anchor else ""),
                    "text": piece if i == 0 else f"{section}\n\n{piece}",
                })
        buf.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        heading = None if fence else HEADING.match(line)
        include = None if fence else INCLUDE.match(line)
        admonition = None if fence else ADMONITION.match(line)
        if heading:
            flush()
            if len(heading.group(1)) == 1:
                title = heading.group(2)
            section, anchor = heading.group(2), heading.group(3) or ""
            buf.append(heading.group(2))
        elif include:
            buf.extend(include_code(include))
        elif admonition:
            if admonition.group(1):
                buf.append(admonition.group(1) + ":")
        else:
            buf.append(line)
    flush()
    return chunks


def build():
    chunks = []
    for md in sorted(DOCS.rglob("*.md")):
        if md.name.startswith("_"):
            continue
        page = md.relative_to(DOCS).as_posix()
        chunks += split_page(page, md.read_text(encoding="utf-8"))
    return chunks


def main():
    chunks = build()
    with OUT.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    sizes = [len(c["text"]) for c in chunks]
    pages = {c["page"] for c in chunks}
    gold = json.loads((ROOT / "evals" / "questions.json").read_text(encoding="utf-8"))
    gold_pages = {p for q in gold["questions"] for p in q.get("gold_pages", [])}
    print(f"{len(chunks)} chunks from {len(pages)} pages -> {OUT}")
    print(f"chars per chunk: median {statistics.median(sizes):.0f}, max {max(sizes)}")
    print(f"gold pages with no chunk: {sorted(gold_pages - pages) or 'none'}")


if __name__ == "__main__":
    main()
