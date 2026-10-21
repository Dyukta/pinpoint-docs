import sys

from pinpoint_docs.answer import MODEL
from scripts.run_eval import load_questions, run

IDS = [16297, 14094, 13973, 16139, 14012, 15819]


def main():
    by_id = {q["id"]: q for q in load_questions()}
    run([by_id[i] for i in IDS], sys.argv[1] if len(sys.argv) > 1 else MODEL, "m2_answers")


if __name__ == "__main__":
    main()
