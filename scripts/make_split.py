import json
import random

from scripts.run_eval import ROOT, load_questions, sample

OUT = ROOT / "evals" / "split.json"
TEST_OTHER = 25


def main():
    questions = load_questions()
    seed0 = sample(questions)
    seed1 = sample(questions, seed=1, exclude={q["id"] for q in seed0})
    dev = [q["id"] for q in seed0 + seed1]
    unused = [q for q in questions if q["id"] not in set(dev) and q["tag"] in ("docs", "bug", "other-library")]
    docs = [q["id"] for q in unused if q["tag"] == "docs"]
    other = [q["id"] for q in random.Random(2).sample([q for q in unused if q["tag"] != "docs"], TEST_OTHER)]
    split = {
        "made_on": "2026-10-21",
        "rule": "dev = every question already used for a decision (the seed 0 and seed 1 samples behind the YES/NO check). test = all docs questions never used for a decision, plus 25 bug or other-library questions never used, picked with seed 2. Tune only on dev; report final numbers only on test.",
        "dev": dev,
        "test": docs + other,
    }
    OUT.write_text(json.dumps(split, indent=1), encoding="utf-8")
    print(f"dev {len(dev)}, test {len(split['test'])} ({len(docs)} docs + {len(other)} others) -> {OUT}")


if __name__ == "__main__":
    main()
