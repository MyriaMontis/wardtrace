"""FastAPI。/api/* と frontend の静的配信（PLAN.md 8章）。

実行：uvicorn backend.main:app --reload
"""

from contextlib import asynccontextmanager
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, queries
from .db import close_driver
from .load import load_all

@asynccontextmanager
async def lifespan(app):
    yield
    close_driver()


app = FastAPI(title="WardTrace", lifespan=lifespan)


class PositiveIn(BaseModel):
    id: str
    test_date: date
    onset_date: Optional[date] = None


class TraceIn(BaseModel):
    index_id: str
    depth: Literal[1, 2] = 2


class AskIn(BaseModel):
    question: str


@app.get("/api/persons")
def persons():
    return [
        {k: p[k] for k in ("id", "name", "kind", "role", "status", "room_id")}
        for p in queries.get_persons()
    ]


@app.get("/api/graph")
def graph():
    return queries.build_graph()


@app.post("/api/positive")
def positive(body: PositiveIn):
    onset = body.onset_date.isoformat() if body.onset_date else None
    p = queries.mark_positive(body.id, body.test_date.isoformat(), onset)
    if p is None:
        raise HTTPException(404, f"person {body.id} not found")
    return p


@app.post("/api/trace")
def trace(body: TraceIn):
    result = queries.trace(body.index_id, body.depth)
    if result is None:
        raise HTTPException(404, f"person {body.index_id} not found")
    return result


@app.get("/api/source")
def source():
    return queries.source()


@app.post("/api/ask")
def ask(body: AskIn):
    return llm.ask(body.question)


@app.post("/api/reset")
def reset():
    return {"ok": True, "contacts": load_all()}


# 静的配信。API のルートより後に置く
app.mount("/vendor", StaticFiles(directory=config.ROOT / "vendor"), name="vendor")
if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/")
    def index_placeholder():
        return JSONResponse({"message": "frontend/ is not built yet. See /docs for the API."})
