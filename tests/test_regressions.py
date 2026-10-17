"""陽性者を追加したときに起きていた漏れ・誤りの回帰テスト（PLAN.md 7章）。

各テストは /api/positive でデータを書き換えるので、前後で /api/reset する。
Neo4j が起動している必要がある。
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        assert c.post("/api/reset").status_code == 200
        yield c
        c.post("/api/reset")


def test_fever_negative_is_never_a_source_candidate(client):
    # P20 は 501号室で P05・P22 と同室。P20 を陽性にすると、発熱陰性の P22 は
    # 潜伏期間内に陽性者2人（P05・P20）と接触したことになる
    res = client.post("/api/positive",
                      json={"id": "P20", "test_date": "2026-10-16", "onset_date": "2026-10-16"})
    assert res.status_code == 200
    rows = client.get("/api/source").json()
    ids = {r["person"]["id"] for r in rows}
    # 同じ部屋の陰性者 P30 は候補に出る（シナリオが成立している確認）
    assert "P30" in ids
    assert "P22" not in ids
    assert "P03" not in ids
    assert rows[0]["person"]["id"] == "N07"


def test_out_of_window_contact_does_not_hide_second_gen(client):
    # P08（P12 と同室）を 10/15 発症で陽性にすると、感染可能期間は 10/13〜10/16。
    # N07 が P08 を担当したのは期間外の 10/12 だけなので1段目には出ないが、
    # 1段目の P12 を期間内に担当しているので2段目には出なければならない
    res = client.post("/api/positive",
                      json={"id": "P08", "test_date": "2026-10-16", "onset_date": "2026-10-15"})
    assert res.status_code == 200
    trace = client.post("/api/trace", json={"index_id": "P08", "depth": 2}).json()
    assert trace["window"] == {"start": "2026-10-13", "end": "2026-10-16"}
    first = {p["id"]: p for p in trace["first_gen"]}
    second = {p["id"]: p for p in trace["second_gen"]}
    assert "N07" not in first
    assert "N07" in second
    via = second["N07"]["via"]
    assert via in first
    # 時間順：2段目の接触は、1段目の接触の1日以上後
    first_contact = min(c["date"] for c in first[via]["contacts"])
    assert min(c["date"] for c in second["N07"]["contacts"]) > first_contact
