"""data/out/*.json を Neo4j に投入し、CONTACT を導出する（PLAN.md 6章）。

実行：python -m backend.load
"""

import json

from . import config
from .db import close_driver, get_driver

CONSTRAINTS = [
    "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT room_id IF NOT EXISTS FOR (r:Room) REQUIRE r.id IS UNIQUE",
]

CREATE_ROOMS = """
UNWIND $rows AS r
CREATE (:Room {id: r.id, name: r.name, type: r.type})
"""

CREATE_PATIENTS = """
UNWIND $rows AS r
CREATE (:Person:Patient {
  id: r.id, name: r.name, age: r.age, sex: r.sex,
  admitted_date: date(r.admitted_date), room_id: r.room_id, status: r.status,
  test_date: date(r.test_date), onset_date: date(r.onset_date),
  isolated_date: date(r.isolated_date), fever_date: date(r.fever_date)
})
"""

CREATE_STAFF = """
UNWIND $rows AS r
CREATE (:Person:Staff {
  id: r.id, name: r.name, role: r.role, status: r.status,
  test_date: date(r.test_date), onset_date: date(r.onset_date),
  isolated_date: date(r.isolated_date)
})
"""

CREATE_STAYS = """
UNWIND $rows AS r
MATCH (p:Person {id: r.patient_id}), (m:Room {id: r.room_id})
CREATE (p)-[:STAYED_IN {date: date(r.date)}]->(m)
"""

CREATE_CARES = """
UNWIND $rows AS r
MATCH (s:Person {id: r.staff_id}), (p:Person {id: r.patient_id})
CREATE (s)-[:CARED_FOR {date: date(r.date), shift: r.shift}]->(p)
"""

CREATE_VISITS = """
UNWIND $rows AS r
MATCH (p:Person {id: r.patient_id}), (m:Room {id: r.room_id})
CREATE (p)-[:VISITED {date: date(r.date), start: r.start, end: r.end}]->(m)
"""

CREATE_SHIFTS = """
UNWIND $rows AS r
MATCH (s:Person {id: r.staff_id}), (m:Room {id: r.room_id})
CREATE (s)-[:WORKED {date: date(r.date), shift: r.shift}]->(m)
"""

# CONTACT は id の小さい方 → 大きい方で作る。同じペア・同じ日・同じ type は1本。
DERIVE_SAME_ROOM = """
MATCH (a:Patient)-[s1:STAYED_IN]->(r:Room)<-[s2:STAYED_IN]-(b:Patient)
WHERE a.id < b.id AND s1.date = s2.date
WITH DISTINCT a, b, s1.date AS d, r.id AS room
MERGE (a)-[c:CONTACT {date: d, type: "same_room"}]->(b)
SET c.minutes = 1440, c.room_id = room, c.close = true
"""

DERIVE_CARE = """
MATCH (s:Staff)-[cf:CARED_FOR]->(p:Patient)
WITH DISTINCT s, p, cf.date AS d
WITH CASE WHEN s.id < p.id THEN s ELSE p END AS a,
     CASE WHEN s.id < p.id THEN p ELSE s END AS b,
     d, p.room_id AS room
MERGE (a)-[c:CONTACT {date: d, type: "care"}]->(b)
SET c.minutes = 30, c.room_id = room, c.close = true
"""

DERIVE_VISIT_OVERLAP = """
MATCH (a:Patient)-[v1:VISITED]->(r:Room)<-[v2:VISITED]-(b:Patient)
WHERE a.id < b.id AND v1.date = v2.date
WITH a, b, r, v1.date AS d,
     toInteger(split(v1.start, ":")[0]) * 60 + toInteger(split(v1.start, ":")[1]) AS s1,
     toInteger(split(v1.end, ":")[0]) * 60 + toInteger(split(v1.end, ":")[1]) AS e1,
     toInteger(split(v2.start, ":")[0]) * 60 + toInteger(split(v2.start, ":")[1]) AS s2,
     toInteger(split(v2.end, ":")[0]) * 60 + toInteger(split(v2.end, ":")[1]) AS e2
WITH a, b, r, d,
     CASE WHEN e1 < e2 THEN e1 ELSE e2 END - CASE WHEN s1 > s2 THEN s1 ELSE s2 END AS overlap
WHERE overlap > 0
WITH a, b, d, max(overlap) AS minutes, collect(r.id)[0] AS room
MERGE (a)-[c:CONTACT {date: d, type: "visit_overlap"}]->(b)
SET c.minutes = minutes, c.room_id = room, c.close = minutes >= 15
"""

DERIVE_SAME_SHIFT = """
MATCH (a:Staff)-[w1:WORKED]->(r:Room)<-[w2:WORKED]-(b:Staff)
WHERE a.id < b.id AND w1.date = w2.date AND w1.shift = w2.shift
WITH DISTINCT a, b, w1.date AS d, r.id AS room
MERGE (a)-[c:CONTACT {date: d, type: "same_shift"}]->(b)
SET c.minutes = 480, c.room_id = room, c.close = false
"""

COUNT_CONTACTS = """
MATCH ()-[c:CONTACT]->()
RETURN c.type AS type, count(*) AS n, sum(CASE WHEN c.close THEN 1 ELSE 0 END) AS close
ORDER BY type
"""


def read_json(name):
    path = config.DATA_DIR / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"{path} がありません。先に python data/generate.py を実行してください")
    with open(path) as f:
        return json.load(f)


def load_all(driver=None):
    """全データを入れ直す。/api/reset からも使う。CONTACT の type 別件数を返す。"""
    driver = driver or get_driver()
    data = {name: read_json(name) for name in
            ("rooms", "patients", "staff", "stays", "cares", "visits", "shifts")}
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
        for q in CONSTRAINTS:
            session.run(q).consume()
        for q, name in ((CREATE_ROOMS, "rooms"), (CREATE_PATIENTS, "patients"),
                        (CREATE_STAFF, "staff"), (CREATE_STAYS, "stays"),
                        (CREATE_CARES, "cares"), (CREATE_VISITS, "visits"),
                        (CREATE_SHIFTS, "shifts")):
            session.run(q, rows=data[name]).consume()
        for q in (DERIVE_SAME_ROOM, DERIVE_CARE, DERIVE_VISIT_OVERLAP, DERIVE_SAME_SHIFT):
            session.run(q).consume()
        return [r.data() for r in session.run(COUNT_CONTACTS)]


def main():
    try:
        counts = load_all()
    finally:
        close_driver()
    print("loaded. CONTACT:")
    for c in counts:
        print(f"  {c['type']:<14} {c['n']:>4}  (close {c['close']})")


if __name__ == "__main__":
    main()
