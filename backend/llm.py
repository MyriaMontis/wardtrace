"""自然文 → Cypher、結果の説明文（PLAN.md 9章）。LLM は ai&（OpenAI 互換）。"""

import json
import re

from neo4j import unit_of_work
from neo4j.exceptions import ClientError
from openai import OpenAI

from . import config
from .db import get_driver

UNAVAILABLE = {"cypher": None, "rows": [], "answer": "LLM unavailable"}

SCHEMA = """\
Nodes:
(:Person:Patient {id, name, age, sex, admitted_date, room_id,
                  status, test_date, onset_date, isolated_date, fever_date})
(:Person:Staff   {id, name, role, status, test_date, onset_date, isolated_date})
(:Room {id, name, type})      // type: "ward" | "xray" | "lab" | "station"

- status: "negative" | "positive" | "fever_negative" | "untested"
- role: "nurse" | "doctor" | "radiographer"
- Dates are Neo4j date values (date("2026-10-14")). Times (start/end) are "HH:MM" strings.
- Patient ids P01-P30, nurses N01-N12, doctors D01-D02, radiographer R01.
- Room ids "501"-"508" (ward), "XRAY", "LAB", "STATION". The data covers 2026-10-10 to 2026-10-16.

Source records:
(:Patient)-[:STAYED_IN {date}]->(:Room)                      // one per day
(:Staff)-[:CARED_FOR {date, shift}]->(:Patient)               // shift: "day" | "night"
(:Patient)-[:VISITED {date, start, end}]->(:Room)            // lab / x-ray visits
(:Staff)-[:WORKED {date, shift}]->(:Room {type:"station"})

Derived (use this for tracing):
(:Person)-[:CONTACT {date, type, minutes, room_id, close}]-(:Person)
- type: "same_room" | "care" | "visit_overlap" | "same_shift"
- Direction has no meaning. Always match it undirected: (a)-[c:CONTACT]-(b)
- close = true for same_room, care, and visit_overlap >= 15 minutes. same_shift is close = false.
"""

PARAMS = """\
- Infectious period starts 2 days before onset (or test date if no onset) and ends at isolated_date.
- Incubation period: 2 to 7 days. A positive person was infected between onset-7 days and onset-2 days.
- Latent period before a contact can infect others: 1 day.
"""

FEW_SHOT = [
    ("P12と濃厚接触した人は？", """\
MATCH (a:Person {id: "P12"})
WITH a, coalesce(a.onset_date, a.test_date) - duration({days: 2}) AS ws,
     coalesce(a.isolated_date, date("2099-12-31")) AS we
MATCH (a)-[c:CONTACT]-(b:Person)
WHERE c.close AND ws <= c.date <= we
RETURN b.id AS id, b.name AS name, b.status AS status,
       collect(DISTINCT c.type) AS types, min(c.date) AS first_contact, max(c.date) AS last_contact
ORDER BY id
LIMIT 50"""),
    ("N07が10/12に担当した患者は？", """\
MATCH (s:Staff {id: "N07"})-[r:CARED_FOR]->(p:Patient)
WHERE r.date = date("2026-10-12")
RETURN p.id AS id, p.name AS name, p.room_id AS room, collect(DISTINCT r.shift) AS shifts
ORDER BY id
LIMIT 50"""),
    ("What do the positive cases have in common?", """\
MATCH (p:Person {status: "positive"})
WITH p, coalesce(p.onset_date, p.test_date) AS ref
MATCH (p)-[c:CONTACT]-(x:Person)
WHERE c.close
  AND ref - duration({days: 7}) <= c.date <= ref - duration({days: 2})
WITH x, collect(DISTINCT p.id) AS linked
WHERE size(linked) >= 2
RETURN x.id AS id, x.name AS name, x.status AS status, linked, size(linked) AS n
ORDER BY n DESC
LIMIT 50"""),
]

SYSTEM_CYPHER = f"""\
You translate questions about a hospital ward contact-tracing graph (Neo4j) into one Cypher query.
Questions may be in Japanese or English.

# Schema
{SCHEMA}
# Parameters
{PARAMS}
# Rules
- READ ONLY. Never use CREATE, MERGE, DELETE, DETACH, SET, REMOVE, DROP, LOAD, CALL or apoc.
- Exactly one statement. Always end with LIMIT 50 (or smaller).
- Write dates as date("YYYY-MM-DD"). "10/12" means date("2026-10-12").
- Match CONTACT undirected.
- Return scalar columns with clear aliases (ids, names, dates, types), not whole nodes or paths.
- Return one row per person (or per entity asked about). Aggregate repeated records with
  collect(DISTINCT ...), min(), max() or count() instead of one row per date.

# Output
Return only JSON: {{"cypher": "..."}}

# Examples
""" + "\n".join(
    f"Q: {q}\nA: {json.dumps({'cypher': c}, ensure_ascii=False)}" for q, c in FEW_SHOT
)

SYSTEM_ANSWER = """\
You explain the result of a Cypher query to a hospital infection control team.
- Answer in the same language as the question (Japanese or English).
- At most 3 sentences. Use only facts in the rows. Mention ids (e.g. N07, P12).
- Do not judge or give instructions (no "should isolate"; say "was in contact with").
- If there are no rows, say that nothing matched.
- Do not add a disclaimer about final decisions.
"""

FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD)\b|\bCALL\s+dbms|apoc",
    re.IGNORECASE,
)
HAS_LIMIT = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)


class UnsafeCypher(ValueError):
    pass


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(base_url=config.AIAND_BASE_URL, api_key=config.AIAND_API_KEY,
                         timeout=60, max_retries=1)
    return _client


def _chat(system, user):
    res = _get_client().chat.completions.create(
        model=config.AIAND_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
    )
    return res.choices[0].message.content or ""


def _extract_cypher(text):
    """LLM の出力から Cypher を取り出す。JSON が基本、コードブロックにも対応。"""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("cypher"), str):
            return obj["cypher"].strip()
        if isinstance(obj, dict) and obj.get("error"):
            # 書き込みの依頼などを LLM 自身が断った
            raise UnsafeCypher(str(obj["error"]))
    m = re.search(r"```(?:cypher)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    raise ValueError(f"no cypher in LLM output: {text[:200]}")


def make_safe(cypher):
    """9-2 の安全策。書き込みを含めば拒否し、LIMIT がなければ付ける。"""
    cypher = cypher.strip().rstrip(";").strip()
    if not cypher:
        raise UnsafeCypher("empty query")
    if ";" in cypher:
        raise UnsafeCypher("multiple statements are not allowed")
    m = FORBIDDEN.search(cypher)
    if m:
        raise UnsafeCypher(f"forbidden keyword: {m.group(0)}")
    if not HAS_LIMIT.search(cypher):
        cypher += "\nLIMIT 50"
    return cypher


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)  # date, duration など


@unit_of_work(timeout=10)
def _run(tx, cypher):
    return [_jsonable(r.data()) for r in tx.run(cypher)]


def run_read_only(cypher):
    """読み取り専用トランザクションで実行する。"""
    with get_driver().session() as s:
        return s.execute_read(_run, cypher)


def generate_cypher(question, error=None, previous=None):
    user = question
    if error:
        user = (f"{question}\n\nYour previous query failed.\nQuery:\n{previous}\n"
                f"Error:\n{error}\nReturn a corrected query.")
    return _extract_cypher(_chat(SYSTEM_CYPHER, user))


JAPANESE = re.compile(r"[぀-ヿ一-鿿]")


def explain(question, cypher, rows):
    payload = json.dumps(rows[:30], ensure_ascii=False, default=str)
    # モデルによっては英語の質問に日本語で答えるので、言語を明示する
    lang = "Japanese" if JAPANESE.search(question) else "English"
    user = (f"Question: {question}\n\nCypher:\n{cypher}\n\n"
            f"Rows ({len(rows)} total, first 30):\n{payload}\n\nAnswer in {lang}.")
    return _chat(SYSTEM_ANSWER, user).strip()


def ask(question):
    if not config.AIAND_API_KEY:
        return dict(UNAVAILABLE)
    cypher = None
    try:
        cypher = generate_cypher(question)
        cypher = make_safe(cypher)
        try:
            rows = run_read_only(cypher)
        except ClientError as e:
            # 構文エラーなどは、エラー文を添えて1回だけ再生成
            cypher = generate_cypher(question, error=e.message, previous=cypher)
            cypher = make_safe(cypher)
            rows = run_read_only(cypher)
    except UnsafeCypher as e:
        return {"cypher": cypher, "rows": [], "answer": f"Query refused (read-only): {e}"}
    except ClientError as e:
        return {"cypher": cypher, "rows": [], "answer": f"Query failed: {e.message}"}
    except ValueError:
        return {"cypher": None, "rows": [], "answer": "Could not build a query for this question."}
    except Exception:
        return dict(UNAVAILABLE)
    try:
        answer = explain(question, cypher, rows)
    except Exception:
        answer = "LLM unavailable"
    return {"cypher": cypher, "rows": rows, "answer": answer}
