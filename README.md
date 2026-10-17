# WardTrace

Contact tracing for hospital-acquired infections (COVID-19 as the model disease).

When a patient tests positive, WardTrace links the records a hospital already has — ward stays, nurse/doctor care and exam-room visits — into a graph, and lists:

- **close contacts** within the infectious window, up to **2 hops**, keeping only **time-respecting chains** (B met C *after* A met B);
- **common-source candidates**: people linked to 2+ positives within each positive's incubation window.

**Decision support only.** WardTrace finds facts in the records; the infection control team (ICT) makes every decision. All data is fictional (one ward, 30 patients, 15 staff, 7 days).

| Sponsor tool | How it is used |
| --- | --- |
| **Neo4j** | Contact graph built from ward records. Multi-hop tracing with infectious-window and time-order constraints, and the common-source search within incubation windows, are Cypher queries — complete and reproducible. |
| **ai&** (OpenAI-compatible inference) | Natural-language questions (English or Japanese) → read-only Cypher → a short answer. The generated Cypher is shown so every query is auditable. Inference runs in Japan, so patient data stays in the country. |

## Why a graph database, not just an LLM

Giving all records to an LLM and asking "list every contact" misses people in thousands of records, gives different answers to the same question (no audit trail), and cannot reliably enforce time order. So **Neo4j does the exact work, and the LLM is only the language layer**. If the LLM is down, the fixed buttons (Trace, Find source) still work because they run Cypher directly.

---

## Quick start

Requirements: Docker Desktop, Python 3.11+ (developed on 3.14), macOS or Linux.

```bash
cp .env.example .env                 # then set AIAND_API_KEY (optional; only "Ask" needs it)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
docker compose up -d                 # Neo4j 5 Community: http://localhost:7474, bolt://localhost:7687
.venv/bin/python data/generate.py    # writes data/out/*.json (fixed seed, same data every time)
.venv/bin/python -m backend.load     # loads JSON into Neo4j and derives CONTACT edges
.venv/bin/python -m uvicorn backend.main:app --port 8000
```

Open **http://localhost:8000**. The API docs (Swagger) are at http://localhost:8000/docs.

Neo4j takes about 10–20 seconds to start after `docker compose up -d`. If `backend.load` fails with a connection error, wait and run it again. Neo4j Browser login: `neo4j` / `wardtrace123`.

### Environment variables (`.env`)

| Name | Default | Meaning |
| --- | --- | --- |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` / `wardtrace123` | Must match `docker-compose.yml` |
| `AIAND_BASE_URL` | `https://api.aiand.com/v1` | ai& endpoint (OpenAI SDK `base_url`) |
| `AIAND_API_KEY` | empty | ai& key. If empty, "Ask" answers `LLM unavailable`; everything else works |
| `AIAND_MODEL` | `openai/gpt-oss-120b` | Backup: `deepseek-ai/deepseek-v4-flash` (both tested) |

`.env` is git-ignored. Never commit API keys.

---

## Screen layout

One screen, designed for 1440×900. Every English label has a short Japanese note in （） next to it.

```
┌──────────────────────────────────────────────────────────────────────┐
│ WardTrace  Ward 5E · Oct 10–16, 2026        [status line]   [Reset]  │  header
├────────────────────┬─────────────────────────────────────────────────┤
│ 1 Mark positive    │                                                 │
│   Person  [▼]      │              graph (Cytoscape.js)               │
│   Test [date]      │                                                 │
│   Onset [date]     │                                                 │
│   [Mark positive]  │  legend (bottom-left of the graph)              │
│ 2 Trace            ├─────────────────────────────────────────────────┤
│   Depth (•1) ( 2)  │  tabs: Contacts | Source | Ask                  │
│   [Trace contacts] │  result panel (tables, answers)                 │
│ 3 Find source      │                                                 │
│   [Find source]    │                                                 │
│ 4 Ask              │                                                 │
│   [question box]   │                                                 │
│   (chip) (chip)    │                                                 │
│   [Ask]            │                                                 │
├────────────────────┴─────────────────────────────────────────────────┤
│ Decision support only. Final decisions are made by the ICT.          │  footer
└──────────────────────────────────────────────────────────────────────┘
```

### Graph legend

| Look | Meaning |
| --- | --- |
| Circle | Patient |
| Rounded square | Staff (nurse, doctor, radiographer) |
| Red fill | Tested positive |
| Large red node in the center | Index case of the current trace |
| Orange fill | 1st generation (close contact of the index within the infectious window) |
| Yellow fill | 2nd generation (time-respecting) |
| Grey fill with dashed border | Had fever but tested negative (never a starting point, never a source candidate) |
| Faded (low opacity) | Not related to the current trace / search |
| Thick red border with a soft glow | Source candidate |
| Blue border | Person mentioned in the latest "Ask" answer |
| Slowly blinking blue glow | Person currently selected in the **Person** dropdown (Step 1), even before marking them positive |
| Line | Close contact (same room, care, or ≥ 15 min overlap in an exam room). One line per pair |

On first load the graph shows all 45 people and 304 close-contact pairs in a force-directed (`cose`) layout. Scroll to zoom, drag the background to pan, drag a node to move it.

---

## How to use it (step by step)

The initial data has two positives, **P05** and **P18**. **P12** (the demo's index case) is still **untested**, but its test date (10/16) and onset date (10/15) are already recorded, so it starts as a grey node. The steps below are the 3-minute demo and the expected results on fresh data. Press **Reset** (top right) any time to restore the initial data.

### Step 1 — Mark positive

1. **Person** dropdown: choose who tested positive. Each option reads `ID Name · room or role · status`, e.g. `P12 Tanaka · room 502 · untested`. P12 is selected on load. The selected person **blinks with a blue glow** in the graph, so you can see who you picked before pressing anything.
2. **Test** date and **Onset** date are filled in automatically when you change the person:
   - a person with recorded dates → those dates (P12: test 2026-10-16, onset 2026-10-15);
   - anyone else → test 2026-10-16, onset empty (onset is optional; without it the test date is used).
3. Click **Mark positive**. This sets the person's status to positive with isolation date = test date (`POST /api/positive`), then **immediately runs Step 2** with the depth currently selected. **P12's node turns from grey to red**, the dropdown now says `positive`, and the status line shows `P12 marked positive (test 10/16, onset 10/15)`, then the trace result.

Marking a new person positive changes the data until you press **Reset**.

### Step 2 — Trace contacts

1. **Depth**: `1` (default) = close contacts only; `2` = also their contacts.
2. Click **Trace contacts**. The index case is the person selected in Step 1 (`POST /api/trace`).
3. The graph explains itself in steps (about 8–10 seconds in total for depth 2). A caption box at the top left of the graph says what each step shows, in English with a Japanese note:
   - **Step 1** — `P12's close contacts in the ward (10/13–10/16): 6 people`. The graph stays in the **original ward layout**, fades everyone else, and zooms in on the index (red) and its 1st generation (orange) with orange lines, so you see where in the ward the contacts are.
   - **Step 2** (depth 2 only) — `Who they met afterwards (time-respecting): 26 people — 34 if time order were ignored`. The 2nd generation turns yellow with yellow lines and the view zooms out to include them.
   - **Step 3** — `Re-arranged around P12: 1st gen inner ring, 2nd gen outer ring`. The nodes move into rings around the index (the abstract view); unrelated people stay faded on the outer edge. With depth 2 the 2nd generation is then shown **faded** (still yellow). The buttons become clickable again when this finishes; the caption disappears a few seconds later.
   - Nodes and the camera move together in every step, and the rings are centered on the index's current spot, so the view does not jump around.
   A small **Ward overview** appears at the top right of the graph: the whole ward in the *original* layout from the first screen, with the same colors, so you can see where the chain sits in the ward. Click it to move the main graph back to the original layout (colors stay); press **Trace contacts** again to return to the index-centered view.
4. The **Contacts** tab opens:
   - Summary line: `Index P12 Tanaka (positive) · infectious window 10/13 → 10/16`. The window is 2 days before onset (or test date) until isolation.
   - Left table **1st generation (6)**: ID, Name, Kind, Status, and close contacts grouped by type with dates and room, e.g. `care: 10/13, 10/14, 10/15, 10/16 (502)`.
   - Right table **2nd generation**: ID, Status, `via` (which 1st-generation person links them), and the contact dates. The heading shows the effect of the time-order rule, e.g. **`26 time-respecting (34 if time order ignored)`**. With depth 1 it says `Set depth 2 to see the second generation.`
   - Click any row to center that person in the graph.
   - A **counts bar** appears above the graph: `P12 1st gen 6 / 2nd gen 26 (34 without time order)` (with a Japanese note). With depth 1 the 2nd gen shows `— (depth 1)`.
   - **Click a 1st-generation node** (depth 2) to see the paths through that person: only the 2nd-generation people reached via them become solid with yellow lines, the other 1st-generation people fade, the counts bar adds `· via N07: 8`, and the 2nd-generation table is filtered (`Showing only 2nd gen via N07: 8 of 26`). Click the same node again, the index, or the background to show all again. Expected: D01 → 3, N05 → 10, N07 → 8, P08 → 6, P25 → 4, R01 → 1 (one person can be reached via several, so these add up to more than 26).
5. Status line: `Traced P12: 6 first-gen, 26 second-gen (34 if time order ignored)`.

Expected for P12 after Step 1 on fresh data: 1st generation = D01, N05, **N07**, P08, P25, R01 (roommates P08 and P25 plus the staff who cared for P12). 2nd generation = 26 with time order, 34 without — **8 people don't fit the time order**, so they drop out of this trace (that does not prove they are uninfected). Example of a removed chain: N10 cared for P25 only on 10/12–10/13, but P25's contact with P12 started on 10/13, so P12 → P25 → N10 is impossible.

### Step 3 — Find source

1. Click **Find source** (`GET /api/source`).
2. The top candidate gets a thick red border and glow; red lines connect it to the positives it is linked to; everything else fades; the view zooms to them.
3. The **Source** tab opens:
   - Summary: `Positives: P05, P12, P18. Fever but test-negative (P03, P22) are neither starting points nor candidates.`
   - Table: rank, ID, Name, Role, Status, **Positives linked** (`3 / 3`), and contacts within each positive's incubation window (2–7 days before onset), e.g. `P05: 10/10 care, 10/11 care, 10/12 care`.
4. Status line: `Top source candidate: N07 (linked to 3 positives)`.

Expected after Step 1 on fresh data: exactly one candidate, **N07 (night nurse, untested)**, linked to all three positives, who are in three different rooms (501, 502, 505). P03 and P22 (fever, test negative) do not appear. If you press Find source *before* marking P12, N07 is still the only candidate but linked to 2 / 2 (P05, P18).

### Step 4 — Ask (ai&)

1. Type a question in the box (English or Japanese), or click a chip: **N07 night shifts** (`Who did N07 care for on night shifts?`) or **P12 roommates (JA)** (`P12と同じ病室にいた患者は？`). Chips send immediately. **Ask** sends the box; ⌘+Enter / Ctrl+Enter also sends. An empty box sends the placeholder question.
2. Wait 2–4 seconds (`Asking ai&…`).
3. The **Ask** tab shows the question, a short answer (max 3 sentences, same language as the question, no instructions or judgments), a collapsible **Cypher run by ai& (read-only) · N rows**, and the result rows as a table.
4. The graph highlights (blue border) every person ID found in the rows or in the question, and fades the rest.

Expected: "Who did N07 care for on night shifts?" → 18 patients (P01, P02, P03, P05, P06, P08, P12, P13, P15, P17, P18, P20, P21, P22, P23, P25, P26, P28). Write requests such as "Delete all data" are refused (`Query refused (read-only): ...`) and the data is unchanged.

### Other interactions

- **Click a node**: the Contacts tab lists that person's close contacts over the whole period (ID, status, contact types, dates). Example: N07 → 18 people.
- **Ward overview** (top right, after a trace): mirrors every highlight (trace, source, ask) on the original layout. Click it to show that layout in the main graph.
- **Reset**: reloads the initial data (`POST /api/reset`), redraws the full graph, clears all tabs, hides the counts bar and sets **Depth back to 1**. The Ward overview is hidden until the next trace.
- **Tabs** can be switched freely; each keeps its last result.

---

## API

All JSON. `/` serves `frontend/index.html`; `/vendor/cytoscape.min.js` is served locally (no CDN needed).

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/api/persons` | — | `[{id, name, kind, role, status, room_id, test_date, onset_date}]` |
| GET | `/api/graph` | — | `{nodes, edges}` in Cytoscape format (all people, close contacts merged per pair) |
| POST | `/api/positive` | `{id, test_date, onset_date?}` | updated person (`status="positive"`, `isolated_date=test_date`); 404 if unknown |
| POST | `/api/trace` | `{index_id, depth: 1\|2}` | `{index, window, first_gen, second_gen, second_gen_if_time_ignored, counts, graph}`. Each 2nd-gen entry has `via` (earliest link) and `vias` (every 1st-gen person linking to them). 404 if unknown, 422 if depth is not 1 or 2 |
| GET | `/api/source` | — | `[{person, linked_positive_ids, n, contacts}]` (max 10, most linked first) |
| POST | `/api/ask` | `{question}` | `{cypher, rows, answer}`; `{cypher: null, rows: [], answer: "LLM unavailable"}` if ai& is not configured or down |
| POST | `/api/reset` | — | reloads the initial data; returns CONTACT counts |

Examples:

```bash
curl -s localhost:8000/api/source
curl -s -X POST localhost:8000/api/trace -H 'content-type: application/json' -d '{"index_id":"P12","depth":2}'
curl -s -X POST localhost:8000/api/ask -H 'content-type: application/json' -d '{"question":"Who did N07 care for on night shifts?"}'
```

### LLM safety (read-only)

Generated Cypher is rejected if it contains `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `LOAD`, `CALL dbms`, `apoc`, or more than one statement. `LIMIT 50` is appended if missing. Queries run in a **read transaction** with a 10-second timeout, so writes fail even if the keyword check were bypassed. On a Cypher error the LLM gets one retry with the error message.

---

## Data and model

Fictional ward 5E, 2026-10-10 to 10-16. Rooms 501–508 (4 beds), X-ray, lab, nurse station. Patients P01–P30, nurses N01–N12 (N01–N06 day, N07–N12 night), doctors D01–D02, radiographer R01. `data/generate.py` uses `random.seed(42)` and checks the scenario before writing.

Scenario: night nurse **N07 (untested)** infected **P05** (room 501, onset 10/14), **P12** (room 502, onset 10/15, the demo's index case — **untested in the initial data** with its test and onset dates recorded; the demo marks it positive) and **P18** (room 505, onset 10/15). Their only common link is N07's night care. **P03** and **P22** had fever but tested negative.

Graph: `(:Person:Patient)`, `(:Person:Staff)`, `(:Room)`; source records `STAYED_IN`, `CARED_FOR`, `VISITED`, `WORKED`; derived `CONTACT {date, type, minutes, room_id, close}` (`same_room`, `care`, `visit_overlap` ≥ 15 min are close; `same_shift` is not).

Disease parameters (COVID-19): infectious from 2 days before onset to isolation; incubation 2–7 days; a contact can pass it on from 1 day later.

The full specification is in [`PLAN.md`](PLAN.md).

## Tests

Neo4j must be running. The tests reload the initial data (`/api/reset`).

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests
```

28 tests: the initial data (P12 untested with dates, N07 linked to 2), the demo scenario after marking P12 positive (P12 turns positive, N07 first with 3, P03/P22 excluded, P12's 1st generation, 26 vs 34, `counts`, `vias`), LLM safety checks (no LLM call needed), and regressions (a fever-negative person linked to two positives is still excluded; an out-of-window contact does not hide someone from the 2nd generation).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Status line shows `Error: ...` or the graph is empty | Neo4j is not running: `docker compose up -d`, wait ~15 s, reload the page |
| Results look different from this README | Someone marked another positive. Press **Reset** |
| Ask says `LLM unavailable` | Set `AIAND_API_KEY` in `.env` and restart the server. Other buttons still work |
| `docker: command not found` on macOS | `export PATH="$HOME/.docker/bin:$PATH"` |

## Repository layout

```
backend/   config.py, db.py, load.py (JSON → Neo4j), queries.py (Cypher), llm.py (ai&), main.py (FastAPI)
data/      generate.py, out/*.json
frontend/  index.html, app.js, style.css (no build step)
tests/     test_scenario.py, test_llm_safety.py, test_regressions.py
vendor/    cytoscape.min.js 3.34.3 (MIT)
```

Built for the +81 Builders hackathon (2026-10-17). The UI is plain HTML/JS; the only front-end library is [Cytoscape.js](https://js.cytoscape.org/) (MIT).
