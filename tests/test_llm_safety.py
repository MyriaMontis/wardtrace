"""PLAN.md 9-2 の安全策。LLM は呼ばない（Neo4j は必要）。"""

import pytest
from neo4j.exceptions import ClientError

from backend import llm


@pytest.mark.parametrize("cypher", [
    "MATCH (n) DETACH DELETE n",
    "CREATE (:Person {id: 'X'})",
    "MATCH (p:Person {id: 'P12'}) SET p.status = 'negative' RETURN p",
    "MERGE (p:Person {id: 'X'}) RETURN p",
    "MATCH (p) REMOVE p.status RETURN p",
    "DROP CONSTRAINT person_id",
    "LOAD CSV FROM 'http://example.com/x.csv' AS r RETURN r",
    "CALL dbms.components()",
    "CALL apoc.help('x')",
    "MATCH (n) RETURN n; MATCH (n) DELETE n",
])
def test_rejects_writes(cypher):
    with pytest.raises(llm.UnsafeCypher):
        llm.make_safe(cypher)


def test_allows_property_names_containing_keywords():
    q = llm.make_safe("MATCH (p:Patient) RETURN p.onset_date AS onset LIMIT 5")
    assert q.endswith("LIMIT 5")


def test_appends_limit():
    q = llm.make_safe("MATCH (p:Patient) RETURN p.id;")
    assert q == "MATCH (p:Patient) RETURN p.id\nLIMIT 50"


def test_read_transaction_blocks_writes_even_if_guard_is_bypassed():
    with pytest.raises(ClientError):
        llm.run_read_only("CREATE (:Person {id: 'SHOULD_NOT_EXIST'})")
    rows = llm.run_read_only("MATCH (p:Person {id: 'SHOULD_NOT_EXIST'}) RETURN count(p) AS n")
    assert rows == [{"n": 0}]


def test_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(llm.config, "AIAND_API_KEY", "")
    assert llm.ask("P12と濃厚接触した人は？") == llm.UNAVAILABLE
