from functools import cache

import numpy as np
import onnxruntime
from tokenizers import Tokenizer

from pinpoint_docs.index import ROOT

MODEL_DIR = ROOT / "data" / "models" / "ms-marco-MiniLM-L6-v2"
MAX_TOKENS = 512


@cache
def load():
    tokenizer = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
    tokenizer.enable_truncation(MAX_TOKENS, strategy="longest_first")
    tokenizer.enable_padding()
    session = onnxruntime.InferenceSession(str(MODEL_DIR / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"])
    return tokenizer, session


def scores(question, texts):
    tokenizer, session = load()
    batch = tokenizer.encode_batch([(question, text) for text in texts])
    feed = {
        "input_ids": np.array([e.ids for e in batch], dtype=np.int64),
        "attention_mask": np.array([e.attention_mask for e in batch], dtype=np.int64),
        "token_type_ids": np.array([e.type_ids for e in batch], dtype=np.int64),
    }
    wanted = {i.name for i in session.get_inputs()}
    return session.run(None, {k: v for k, v in feed.items() if k in wanted})[0][:, 0]


def rerank(question, texts):
    return [int(i) for i in np.argsort(-scores(question, texts))]
