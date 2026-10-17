"""接触追跡・感染源推定・画面用グラフの Cypher（PLAN.md 7章）。"""

from datetime import date, timedelta

from neo4j.time import Date

from . import config
from .db import get_driver

TRACE = """
MATCH (a:Person {id: $index_id})
WITH a,
     coalesce(a.onset_date, a.test_date) - duration({days: $lookback}) AS ws,
     coalesce(a.isolated_date, date("2099-12-31")) AS we
MATCH (a)-[c1:CONTACT]-(b:Person)
WHERE c1.close AND ws <= c1.date <= we
OPTIONAL MATCH (b)-[c2:CONTACT]-(c:Person)
WHERE $depth >= 2 AND c2.close AND c <> a
  AND c2.date >= c1.date + duration({days: $latent})
  AND NOT (a)-[:CONTACT {close: true}]-(c)
RETURN a, ws, we, b, collect(DISTINCT c1) AS c1s,
       collect(DISTINCT {person: c, edge: c2}) AS second
"""

SOURCE = """
MATCH (p:Person {status: "positive"})
WITH p, coalesce(p.onset_date, p.test_date) AS ref
MATCH (p)-[c:CONTACT]-(x:Person)
WHERE c.close
  AND ref - duration({days: $inc_max}) <= c.date <= ref - duration({days: $inc_min})
WITH x, collect(DISTINCT p.id) AS linked,
     collect({date: c.date, type: c.type, minutes: c.minutes, room_id: c.room_id,
              positive_id: p.id}) AS edges
WHERE size(linked) >= 2
RETURN x, linked, size(linked) AS n, edges
ORDER BY n DESC, x.id
LIMIT 10
"""

PERSONS = "MATCH (p:Person) RETURN p ORDER BY p.id"

PERSON = "MATCH (p:Person {id: $id}) RETURN p"

CLOSE_EDGES = """
MATCH (a:Person)-[c:CONTACT]->(b:Person)
WHERE c.close
RETURN a.id AS source, b.id AS target, collect(c.type) AS types, collect(c.date) AS dates
"""

MARK_POSITIVE = """
MATCH (p:Person {id: $id})
SET p.status = "positive",
    p.test_date = date($test_date),
    p.onset_date = CASE WHEN $onset_date IS NULL THEN p.onset_date ELSE date($onset_date) END,
    p.isolated_date = date($test_date)
RETURN p
"""

# 1本のペアに複数の type があるとき、画面に出す type の優先順
TYPE_ORDER = ["care", "same_room", "visit_overlap", "same_shift"]


def _val(v):
    return v.iso_format() if isinstance(v, Date) else v


def _kind(node):
    return "staff" if "Staff" in node.labels else "patient"


def person(node):
    """Person ノード → JSON。日付は "YYYY-MM-DD"。"""
    d = {k: _val(v) for k, v in dict(node).items()}
    d["kind"] = _kind(node)
    d.setdefault("role", None)
    d.setdefault("room_id", None)
    return d


def _brief(node):
    return {"id": node["id"], "name": node["name"], "kind": _kind(node),
            "status": node["status"]}


def contact(rel, full=True):
    d = {"date": _val(rel["date"]), "type": rel["type"]}
    if full:
        d["minutes"] = rel["minutes"]
        d["room_id"] = rel["room_id"]
    return d


def _read(cypher, **params):
    with get_driver().session() as s:
        return s.execute_read(lambda tx: list(tx.run(cypher, **params)))


def _write(cypher, **params):
    with get_driver().session() as s:
        return s.execute_write(lambda tx: list(tx.run(cypher, **params)))


def get_persons():
    return [person(r["p"]) for r in _read(PERSONS)]


def get_person(pid):
    rows = _read(PERSON, id=pid)
    return person(rows[0]["p"]) if rows else None


def mark_positive(pid, test_date, onset_date=None):
    rows = _write(MARK_POSITIVE, id=pid, test_date=test_date, onset_date=onset_date)
    return person(rows[0]["p"]) if rows else None


def build_graph(gen=None, trace_edges=None):
    """全 Person と close な CONTACT（ペアごとに1本にまとめる）を Cytoscape 形式で返す。

    gen: {id: 0|1|2}。ないものは null（無関係）。
    trace_edges: {(id, id): {"type", "date"}}。追跡で辿った辺。trace=true を付け、
                 type/date は追跡で使った接触のものにする。
    """
    gen = gen or {}
    trace_edges = trace_edges or {}
    nodes = []
    for p in get_persons():
        nodes.append({"data": {
            "id": p["id"], "label": p["id"], "name": p["name"], "kind": p["kind"],
            "role": p["role"], "room_id": p["room_id"], "status": p["status"],
            "gen": gen.get(p["id"]),
        }})
    edges = []
    for r in _read(CLOSE_EDGES):
        types = sorted(set(r["types"]), key=TYPE_ORDER.index)
        dates = sorted({_val(d) for d in r["dates"]})
        key = tuple(sorted((r["source"], r["target"])))
        t = trace_edges.get(key)
        edges.append({"data": {
            "id": f"{key[0]}-{key[1]}", "source": r["source"], "target": r["target"],
            "type": t["type"] if t else types[0], "types": types,
            "date": t["date"] if t else dates[0], "dates": dates,
            "close": True, "trace": bool(t),
        }})
    return {"nodes": nodes, "edges": edges}


def _earliest(contacts):
    return min(contacts, key=lambda c: c["date"])


def trace(index_id, depth=2):
    """接触者追跡（7-1）。index がいなければ None。"""
    index = get_person(index_id)
    if index is None:
        return None
    rows = _read(TRACE, index_id=index_id, depth=depth,
                 lookback=config.INFECTIOUS_LOOKBACK_DAYS, latent=config.LATENT_DAYS)
    ref = index.get("onset_date") or index.get("test_date")
    window = {"start": None, "end": None}
    if ref:
        start = date.fromisoformat(ref) - timedelta(days=config.INFECTIOUS_LOOKBACK_DAYS)
        window = {"start": start.isoformat(), "end": index.get("isolated_date") or "2099-12-31"}

    first, second = {}, {}
    for r in rows:
        b = r["b"]
        contacts = sorted((contact(c) for c in r["c1s"]), key=lambda c: c["date"])
        first[b["id"]] = {**_brief(b), "contacts": contacts}
        for s in r["second"]:
            c, e = s["person"], s["edge"]
            if c is None:
                continue
            entry = second.setdefault(c["id"], {**_brief(c), "via_all": {}})
            entry["via_all"].setdefault(b["id"], []).append(contact(e, full=False))

    second_gen = []
    for cid, entry in second.items():
        if cid in first or cid == index_id:
            continue
        # via は最も早く接触した1段目の人
        via, cs = min(entry.pop("via_all").items(), key=lambda kv: _earliest(kv[1])["date"])
        second_gen.append({**entry, "via": via,
                           "contacts": sorted(cs, key=lambda c: c["date"])})

    first_gen = sorted(first.values(), key=lambda p: p["id"])
    second_gen.sort(key=lambda p: p["id"])

    gen = {index_id: 0}
    gen.update({p["id"]: 1 for p in first_gen})
    gen.update({p["id"]: 2 for p in second_gen})
    trace_edges = {}
    for p in first_gen:
        trace_edges[tuple(sorted((index_id, p["id"])))] = _earliest(p["contacts"])
    for p in second_gen:
        trace_edges[tuple(sorted((p["via"], p["id"])))] = _earliest(p["contacts"])

    return {
        "index": {"id": index["id"], "name": index["name"], "kind": index["kind"],
                  "status": index["status"]},
        "window": window,
        "first_gen": first_gen,
        "second_gen": second_gen,
        "graph": build_graph(gen, trace_edges),
    }


def source():
    """感染源の推定（7-2）。"""
    rows = _read(SOURCE, inc_max=config.INCUBATION_MAX_DAYS,
                 inc_min=config.INCUBATION_MIN_DAYS)
    out = []
    for r in rows:
        contacts = [{k: _val(v) for k, v in e.items()} for e in r["edges"]]
        contacts.sort(key=lambda c: (c["date"], c["positive_id"]))
        out.append({
            "person": person(r["x"]),
            "linked_positive_ids": sorted(r["linked"]),
            "n": r["n"],
            "contacts": contacts,
        })
    return out
