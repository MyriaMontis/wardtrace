# WardTrace

Contact tracing for hospital-acquired infections. When a patient tests positive, WardTrace links ward stays, nurse/doctor care and exam-room visits in a graph, and lists close-contact chains (time-respecting, up to 2 hops) and common-source candidates.

Decision support only. Final decisions are made by the infection control team (ICT).

- **Neo4j**: contact graph, infectious-window and incubation-window queries
- **ai&**: natural-language questions → read-only Cypher, plus a short explanation

All data is fictional.

## Setup

```bash
cp .env.example .env          # set AIAND_API_KEY
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
docker compose up -d          # Neo4j at http://localhost:7474 (neo4j / wardtrace123)
.venv/bin/python data/generate.py
.venv/bin/python -m backend.load
```
