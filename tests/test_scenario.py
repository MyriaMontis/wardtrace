"""PLAN.md 5章「期待される結果」を API で確かめる。

Neo4j が起動している必要がある（docker compose up -d）。
各テストの前に /api/reset で初期データを入れ直す。初期データの P12 は untested で、
デモと同じく Mark positive（検査 10/16・発症 10/15）してから追跡・推定する。
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app

DEMO_POSITIVE = {"id": "P12", "test_date": "2026-10-16", "onset_date": "2026-10-15"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        assert c.post("/api/reset").status_code == 200
        yield c
        c.post("/api/reset")


@pytest.fixture
def demo(client):
    """デモの手順1：P12 を陽性にした状態。"""
    res = client.post("/api/positive", json=DEMO_POSITIVE)
    assert res.status_code == 200
    return client


def test_initial_data_p12_is_untested_with_dates(client):
    p12 = next(p for p in client.get("/api/persons").json() if p["id"] == "P12")
    assert p12["status"] == "untested"
    assert p12["test_date"] == "2026-10-16"
    assert p12["onset_date"] == "2026-10-15"
    positives = sorted(p["id"] for p in client.get("/api/persons").json() if p["status"] == "positive")
    assert positives == ["P05", "P18"]


def test_initial_source_is_n07_with_two_positives(client):
    rows = client.get("/api/source").json()
    assert [r["person"]["id"] for r in rows] == ["N07"]
    assert rows[0]["n"] == 2
    assert rows[0]["linked_positive_ids"] == ["P05", "P18"]


def test_mark_positive_turns_p12_positive(client):
    p = client.post("/api/positive", json=DEMO_POSITIVE).json()
    assert p["status"] == "positive"
    assert p["isolated_date"] == "2026-10-16"
    node = next(n["data"] for n in client.get("/api/graph").json()["nodes"] if n["data"]["id"] == "P12")
    assert node["status"] == "positive"  # 画面ではこれで赤くなる


def test_source_n07_is_first(demo):
    rows = demo.get("/api/source").json()
    assert rows, "no source candidates"
    top = rows[0]
    assert top["person"]["id"] == "N07"
    assert top["n"] == 3
    assert top["linked_positive_ids"] == ["P05", "P12", "P18"]
    assert top["person"]["status"] == "untested"


def test_source_excludes_fever_negatives(demo):
    ids = {r["person"]["id"] for r in demo.get("/api/source").json()}
    assert not ids & {"P03", "P22"}


@pytest.mark.parametrize("depth", [1, 2])
def test_trace_p12_first_gen(demo, depth):
    res = demo.post("/api/trace", json={"index_id": "P12", "depth": depth}).json()
    assert res["index"]["id"] == "P12"
    assert res["index"]["status"] == "positive"
    assert res["window"] == {"start": "2026-10-13", "end": "2026-10-16"}
    first = {p["id"]: p for p in res["first_gen"]}
    assert sorted(first) == ["D01", "N05", "N07", "P08", "P25", "R01"]
    assert any(c["type"] == "care" for c in first["N07"]["contacts"])
    # 同室（502号室）の患者も1段目に出る
    roommates = {p["id"] for p in demo.get("/api/persons").json()
                 if p["room_id"] == "502" and p["id"] != "P12"}
    assert roommates and roommates <= set(first)
    gens = {n["data"]["id"]: n["data"]["gen"] for n in res["graph"]["nodes"]}
    assert gens["P12"] == 0 and gens["N07"] == 1


def test_trace_depth1_has_no_second_gen(demo):
    res = demo.post("/api/trace", json={"index_id": "P12", "depth": 1}).json()
    assert res["second_gen"] == []
    assert res["second_gen_if_time_ignored"] is None


def test_time_order_removes_false_chains(demo):
    # P12 起点：時間順を守ると2段目は26人、無視すると34人（8人の偽の連鎖を除ける）
    res = demo.post("/api/trace", json={"index_id": "P12", "depth": 2}).json()
    assert len(res["second_gen"]) == 26
    assert res["second_gen_if_time_ignored"] == 34


def test_trace_unknown_person(client):
    assert client.post("/api/trace", json={"index_id": "X99", "depth": 1}).status_code == 404
