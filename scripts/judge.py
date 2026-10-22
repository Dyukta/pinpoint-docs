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


def judge(row, question, chunks, model):
    hits = [chunks[i] for i in row.get("retrieved", []) if i in chunks]
    fields = {
        "question": query_text(question, full=True),
        "reference": question["answer"],
        "answer": row["answer"],
        "excerpts": excerpts(hits),
    }
    out = {}
    for metric, (system, user) in ASK.items():
        if metric == "faithful" and not hits:
            continue
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
    run, system = sys.argv[1], sys.argv[2]
    rows = json.loads((ROOT / "evals" / run).read_text(encoding="utf-8"))["results"]
    questions = {q["id"]: q for q in load_questions()}
    chunks = {c["id"]: c for c in load_chunks()}
    hand = json.loads((ROOT / "evals" / "hand_grades.json").read_text(encoding="utf-8"))
    correct_hand = {g["id"]: HAND[g[system]] for g in hand["grades"] if g[system] in HAND}
    checks_hand = {g["id"]: g for g in hand.get("answer_checks", [])} if system == "pinpoint" else {}

    judged = []
    for row in rows:
        if row["answer"].strip() == IDK or row.get("said_idk"):
            continue
        verdicts = judge(row, questions[row["id"]], chunks, MODEL)
        judged.append({"id": row["id"], "tag": row["tag"], **verdicts})
        print(f"#{row['id']} {row['tag']:<13} " + "  ".join(f"{k} {v}" for k, v in verdicts.items()), flush=True)

    out = ROOT / "evals" / f"judged_{run}"
    out.write_text(json.dumps({"run": run, "judge": MODEL, "results": judged}, indent=1), encoding="utf-8")
    print(f"\n{len(judged)} answers judged -> {out.name}")
    for metric in ASK:
        values = [j[metric] for j in judged if metric in j]
        if values:
            print(f"{metric}: {dict(Counter(values))}")
    print("\nagreement with hand grades:")
    print(
        f"  correct:  {agreement([(j['correct'], correct_hand[j['id']]) for j in judged if j['id'] in correct_hand])}"
    )
    print(
        f"  faithful: {agreement([(j['faithful'], checks_hand[j['id']]['faithful']) for j in judged if j['id'] in checks_hand and 'faithful' in j])}"
    )
    print(
        f"  relevant: {agreement([(j['relevant'], checks_hand[j['id']]['relevant']) for j in judged if j['id'] in checks_hand])}"
    )


if __name__ == "__main__":
    main()
