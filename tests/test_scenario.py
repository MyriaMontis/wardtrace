"""PLAN.md 5章「期待される結果」を API で確かめる。

Neo4j が起動している必要がある（docker compose up -d）。
最初に /api/reset で初期データを入れ直す。
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        assert c.post("/api/reset").status_code == 200
        yield c


def test_source_n07_is_first(client):
    rows = client.get("/api/source").json()
    assert rows, "no source candidates"
    top = rows[0]
    assert top["person"]["id"] == "N07"
    assert top["n"] == 3
    assert top["linked_positive_ids"] == ["P05", "P12", "P18"]
    assert top["person"]["status"] == "untested"


def test_source_excludes_fever_negatives(client):
    ids = {r["person"]["id"] for r in client.get("/api/source").json()}
    assert not ids & {"P03", "P22"}


@pytest.mark.parametrize("depth", [1, 2])
def test_trace_p12_first_gen(client, depth):
    res = client.post("/api/trace", json={"index_id": "P12", "depth": depth}).json()
    assert res["index"]["id"] == "P12"
    assert res["window"] == {"start": "2026-10-13", "end": "2026-10-16"}
    first = {p["id"]: p for p in res["first_gen"]}
    assert "N07" in first
    assert any(c["type"] == "care" for c in first["N07"]["contacts"])
    # 同室（502号室）の患者も1段目に出る
    roommates = {p["id"] for p in client.get("/api/persons").json()
                 if p["room_id"] == "502" and p["id"] != "P12"}
    assert roommates and roommates <= set(first)
    gens = {n["data"]["id"]: n["data"]["gen"] for n in res["graph"]["nodes"]}
    assert gens["P12"] == 0 and gens["N07"] == 1


def test_trace_depth1_has_no_second_gen(client):
    res = client.post("/api/trace", json={"index_id": "P12", "depth": 1}).json()
    assert res["second_gen"] == []
    assert res["second_gen_if_time_ignored"] is None


def test_time_order_removes_false_chains(client):
    # P12 起点：時間順を守ると2段目は26人、無視すると34人（8人の偽の連鎖を除ける）
    res = client.post("/api/trace", json={"index_id": "P12", "depth": 2}).json()
    assert len(res["second_gen"]) == 26
    assert res["second_gen_if_time_ignored"] == 34


def test_trace_unknown_person(client):
    assert client.post("/api/trace", json={"index_id": "X99", "depth": 1}).status_code == 404
