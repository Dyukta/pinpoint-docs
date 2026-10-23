import json
import re
import sys
from collections import Counter

from pinpoint_docs.answer import IDK, MODEL, chat, excerpts
from pinpoint_docs.index import load_chunks
from scripts.compare_retrieval import query_text
from scripts.run_eval import ROOT, load_questions

ASK = {
    "faithful": (
        "You check whether an answer is supported by documentation excerpts. Reply with only YES, PARTLY or NO.",
        "Excerpts:\n\n{excerpts}\n\nAnswer:\n{answer}\n\nIs every claim and every line of code in the answer supported by the excerpts? Reply YES, PARTLY or NO.",
    ),
    "relevant": (
        "You check whether an answer addresses a question. Reply with only YES, PARTLY or NO.",
        "Question:\n{question}\n\nAnswer:\n{answer}\n\nDoes the answer address what the question asks? Reply YES, PARTLY or NO.",
    ),
    "correct": (
        "You compare an answer with a reference answer written by an expert. Reply with only YES, PARTLY or NO.",
        "Question:\n{question}\n\nReference answer:\n{reference}\n\nAnswer:\n{answer}\n\nDoes the answer agree with the reference answer? Reply YES, PARTLY or NO.",
    ),
}
HAND = {"correct": "yes", "partly": "partly", "wrong": "no"}


def verdict(text):
    words = re.findall(r"[A-Z]+", text.upper())
    return words[0].lower() if words and words[0] in ("YES", "PARTLY", "NO") else "unclear"


def judge(row, question, chunks, model, metrics=tuple(ASK)):
    hits = [chunks[i] for i in row.get("retrieved", []) if i in chunks]
    fields = {
        "question": query_text(question, full=True),
        "reference": question["answer"],
        "answer": row["answer"],
        "excerpts": excerpts(hits),
    }
    out = {}
    for metric in metrics:
        if metric == "faithful" and not hits:
            continue
        system, user = ASK[metric]
        reply = chat(model, system, user.format(**fields), num_predict=3)
        out[metric] = verdict(reply["message"]["content"])
    return out


def agreement(pairs):
    if not pairs:
        return "no hand grades"
    exact = sum(a == b for a, b in pairs)
    yes_no = sum((a == "yes") == (b == "yes") for a, b in pairs)
    return f"exact {exact}/{len(pairs)}, yes vs not-yes {yes_no}/{len(pairs)}"


def main():
    run, system, flags = sys.argv[1], sys.argv[2], sys.argv[3:]
    model = next((a for a in flags if a not in ("correct", "hand")), MODEL)
    metrics = ["correct"] if "correct" in flags else list(ASK)
    rows = json.loads((ROOT / "evals" / run).read_text(encoding="utf-8"))["results"]
    questions = {q["id"]: q for q in load_questions()}
    chunks = {c["id"]: c for c in load_chunks()}
    hand = json.loads((ROOT / "evals" / "hand_grades.json").read_text(encoding="utf-8"))
    correct_hand = {g["id"]: HAND[g[system]] for g in hand["grades"] if g[system] in HAND}
    checks_hand = {g["id"]: g for g in hand.get("answer_checks", [])} if system == "pinpoint" else {}

    out = ROOT / "evals" / (f"judged_{run}" if model == MODEL else f"judged_{model}_{run}")
    done = {j["id"]: j for j in json.loads(out.read_text(encoding="utf-8"))["results"]} if out.exists() else {}
    judged = []
    for row in rows:
        if row["answer"].strip() == IDK or row.get("said_idk"):
            continue
        if "hand" in flags and row["id"] not in correct_hand:
            continue
        if row["id"] in done:
            judged.append(done[row["id"]])
            continue
        verdicts = judge(row, questions[row["id"]], chunks, model, metrics)
        judged.append({"id": row["id"], "tag": row["tag"], **verdicts})
        out.write_text(json.dumps({"run": run, "judge": model, "results": judged}, indent=1), encoding="utf-8")
        print(f"#{row['id']} {row['tag']:<13} " + "  ".join(f"{k} {v}" for k, v in verdicts.items()), flush=True)

    print(f"\n{len(judged)} answers judged ({len(done)} from an earlier run) -> {out.name}")
    for metric in metrics:
        values = [j[metric] for j in judged if metric in j]
        if values:
            print(f"{metric}: {dict(Counter(values))}")
    print("\nagreement with hand grades:")
    for metric in metrics:
        hand_grade = correct_hand if metric == "correct" else {i: g[metric] for i, g in checks_hand.items()}
        pairs = [(j[metric], hand_grade[j["id"]]) for j in judged if j["id"] in hand_grade and metric in j]
        print(f"  {metric}: {agreement(pairs)}")


if __name__ == "__main__":
    main()
