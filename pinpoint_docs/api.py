from fastapi import FastAPI
from pydantic import BaseModel, Field

from pinpoint_docs.answer import answer

app = FastAPI(title="Pinpoint", summary="Answers FastAPI questions from the FastAPI docs, with links, or says I don't know.")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=20000)


class Answer(BaseModel):
    trace_id: str
    answer: str
    sources: list[str]
    cached: bool


@app.post("/ask")
def ask(body: Question) -> Answer:
    return Answer(**answer(body.question))
