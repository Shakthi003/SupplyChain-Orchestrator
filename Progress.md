# SupplyChain Orchestrator — Learning Journal

> This file is a narrative log: what we did, how we did it, and why.
> Written like a learning journal — theory + reasoning behind every decision.

---

## Session 1 — Project Understanding & Tech Stack Decisions

### What we did

- Read through the full project plan document (`SupplyChain_Sentinel_Project_Plan.docx`)
- Understood the vision: an AI platform that detects supply chain disruptions, traces their downstream impact, estimates risk, proposes recovery options, and always keeps a human in control of the final decision
- Decided on the full tech stack

### How we did it

- Went through all 18 sections of the plan document
- Asked clarifying questions about preferences (LLM, package manager, vector store, DBs)
- Made decisions based on: free-to-use, easy-to-learn, industry-relevant

### Tech Stack Decisions & Why

**LLM: Gemini 3.8 Flash (Google AI Studio — free tier)**

- Chosen over Ollama (local) because Ollama is slow without a GPU — can take 10–60 seconds per response on a laptop
- Gemini is free (60 req/min), responds in 1–3 seconds via API
- We originally planned Gemini 1.5 Flash but Google has since deprecated it; the latest available free model is Gemini 3.8 Flash — model names change but the integration code stays the same
- LangChain supports Gemini natively — swapping models later is a one-line change in `core/config.py`

**Package Manager: uv**

- Replaces both `pip` and `venv` — handles virtual environments + package installation together
- 10–100x faster than pip
- Very new but rapidly becoming the Python ecosystem standard

**Vector Store: ChromaDB**

- Used for RAG (Retrieval-Augmented Generation) — storing and searching document embeddings
- Free, runs locally, no server needed, installs with a single pip command
- Best choice for a learning-phase prototype

**Relational DB: PostgreSQL 16**

- Free, open source, industry standard
- Stores structured data: suppliers, purchase orders, inventory, production orders, etc.
- Installed via official EDB installer; Stack Builder popup at the end is optional and was cancelled

**Graph DB: Neo4j Desktop 2.2.1 (free)**

- Stores *relationships* between entities — e.g., Supplier → Part → Production Order → Customer
- Regular databases struggle with multi-hop queries like "which customers are affected by this supplier delay?" — Neo4j answers it in one simple Cypher query
- Created a local instance named `supplychain` running Neo4j version 2026.09.0

**Agent Orchestration: LangGraph + LangChain**

- LangGraph lets us build stateful, step-by-step AI workflows with branching and human approval gates
- This is exactly what we need: validate event → trace impact → score risk → plan recovery → explain → human approves

---

## Session 2 — Environment Setup & Verification

### What we did

- Verified Python 3.11.9 and uv 0.12.17 were already installed
- Installed PostgreSQL 16.15 and created the `supplychain` database
- Installed Neo4j Desktop, created a local instance named `supplychain`, got it running
- Obtained a Gemini API key from Google AI Studio (free tier)
- Verified all three services connect successfully from Python

### How we did it

**PostgreSQL:**

- Installed via the official EDB Windows installer
- Service `postgresql-x64-16` runs automatically on startup
- Created the `supplychain` database using `createdb`
- Verified connection using SQLAlchemy + psycopg2 from Python — got back `PostgreSQL 16.15`

**Neo4j:**

- Installed Neo4j Desktop 2.2.1
- Created a local instance: name = `supplychain`, version = 2026.09.0
- Started the instance — status showed green "RUNNING"
- Password mismatch caused first connection failure — fixed by updating `.env` to match the password set in Neo4j Desktop
- Verified with Python neo4j driver — `RETURN 'Neo4j is connected and working!'` returned successfully

**Gemini API:**

- API key obtained from https://aistudio.google.com/app/apikey — project named `supplychain`
- Key format is `AQ.xxx...` (newer Google format, not `AIzaSy...` — both are valid)
- Model `gemini-1.5-flash` was tried first — deprecated for new users
- Model `gemini-2.5-flash` was tried next — also unavailable for new users
- Final working model: **`gemini-3.8-flash`** (Google's latest free Flash model)
- Verified with a live API call — received correct response

### Key files created

- `scripts/check_connections.py` — tests PostgreSQL connection
- `scripts/check_neo4j.py` — tests Neo4j connection
- `scripts/check_gemini.py` — tests Gemini API

---

## Session 3 — Repository Scaffold & Project Structure

### What we did

- Created the full project folder structure
- Created `pyproject.toml` (project definition + all dependencies)
- Created `core/config.py` (loads all secrets from `.env` into Python variables)
- Created `.env.example` (safe template showing what secrets are needed, no real values)
- Created `.gitignore` (tells Git never to commit `.env`, `.venv/`, cache files)
- Ran `uv sync` to install all 184 Python packages into a virtual environment

### How we did it & Why

**Folder structure — why this layout?**
Each folder is one "concern". When something breaks, you know exactly where to look:

```
app/              → Streamlit UI only — nothing else
api/              → FastAPI endpoints only
core/             → All calculation logic (no AI, no DB calls here)
agents/           → LangGraph AI workflow only
retrieval/        → ChromaDB + RAG only
graph/            → Neo4j queries only
tools/            → MCP tool definitions only
data/             → Raw synthetic data files
evaluation/       → Metrics and test harness
tests/            → pytest unit and integration tests
scripts/          → One-off helper scripts (not part of the app)
docs/             → Architecture diagrams, decisions
```

**pyproject.toml — why not requirements.txt?**
`pyproject.toml` is the modern Python standard (PEP 518/621). It handles:

- Project metadata (name, version, Python version requirement)
- All runtime dependencies with minimum versions
- Dev-only dependencies (pytest, ruff linter) in a separate group
- Build system configuration
  `requirements.txt` only handles one of these. `pyproject.toml` does everything in one file.

**core/config.py — why a separate config file?**
Every module that needs a secret (DB password, API key) imports from `config.py` instead of calling `load_dotenv()` itself. This means:

- Secrets are loaded exactly once
- If you rename an env variable, you change it in one place
- Easy to see all configuration in one glance

**uv sync — what it actually does:**

1. Reads `pyproject.toml`
2. Resolves all dependencies (finds versions that don't conflict with each other)
3. Creates `.venv/` virtual environment (isolated Python environment for this project)
4. Downloads and installs all 184 packages
5. The biggest download was `torch` (118MB) — pulled in by `sentence-transformers` for generating embeddings locally

### Problem encountered & fixed

- `uv sync` first failed because hatchling (the build tool) couldn't find a package folder named `supplychain_orchestrator`
- Fix: added `[tool.hatch.build.targets.wheel]` section to `pyproject.toml` pointing to our actual source folders
- Second run succeeded

---

## Session 4 — Stage 2: Database Schema & Synthetic Data

### What we did

- Designed and created 10 PostgreSQL tables using SQLAlchemy ORM models
- Wrote a synthetic data generator with `--reset`, `--seed`, and `--scenario` flags
- Injected a deliberate disruption scenario for testing
- Verified all 109 rows loaded correctly across all 10 tables

### Files created

- `core/models.py` — 10 SQLAlchemy model classes (one per table), 6 enums for fixed-value columns
- `scripts/init_db.py` — creates all 10 tables in PostgreSQL from the models (`Base.metadata.create_all`)
- `scripts/generate_data.py` — fills the tables with realistic synthetic data

### How the 3 files relate

```
core/models.py       → DESCRIBES the structure (pure Python, no DB interaction)
scripts/init_db.py   → BUILDS the empty tables in PostgreSQL (runs CREATE TABLE)
scripts/generate_data.py → FILLS those tables with rows (runs INSERT INTO)
```

### The test scenario we embedded

- **SUP-005 (Apex Hydraulics)** notified a 4-day delay on PO-441
- **PRT-104 (Hydraulic Valve)** — the delayed part — has only 35 units available across all warehouses
- **WH-01**: 45 on hand − 30 reserved = 15 available
- **WH-02**: 20 on hand − 0 reserved = 20 available (backup, usable for transfer)
- **Known correct answers** baked in so we can verify the engine later:
  - PRD-301, PRD-302 → AT RISK (both products need PRT-104 via BOM)
  - PRD-303 → SAFE (its product FGD-204 does not use PRT-104)
  - CO-501 (Acme), CO-502 (GlobalTech) → AT RISK
  - CO-503 (Precision Works) → SAFE

### Problem encountered

- `datetime.utcnow()` deprecated in Python 3.12 — showed warnings but did not break anything
- Will fix properly when we refactor with timezone-aware datetimes

---

## Session 5 — Stage 3: Deterministic Impact Engine

### What we did

- Built a 4-file pipeline that reads a disruption event and produces a full impact report
- Validated the output against the known correct answers — **all 7 checks passed**

### Files created

- `core/impact_analysis/inventory.py` — calculates available stock, coverage days, shortage date
- `core/impact_analysis/bom_tracer.py` — traces which products use the delayed component
- `core/impact_analysis/order_impact.py` — finds affected production orders and customer orders
- `core/impact_analysis/engine.py` — orchestrates all 3, prints report, validates output

### How the pipeline works (step by step)

```
1. engine.py reads EVT-001 from DB
2. Finds SHP-441 → PO-441 → PRT-104 (the delayed part)
3. bom_tracer.py: "Which products use PRT-104?"
   → FGD-201 needs 2x, FGD-203 needs 1x
4. order_impact.py: "Which production orders build those products?"
   → PRD-301 (25 units FGD-201), PRD-302 (15 units FGD-203)
   → Daily consumption = 72.5 units/day
5. inventory.py: "Do we have enough stock?"
   → 35 available ÷ 72.5/day = 0.5 days coverage
   → SHORTAGE on Oct 20 (tomorrow!)
   → Shipment arrives Oct 29 → 8.5 day gap → SHORTAGE CONFIRMED
6. Report printed + validation run
```

### What "deterministic" means and why it matters

- Deterministic = pure math + DB queries. No AI involved.
- Same input always gives exactly the same output.
- Numbers are always correct and auditable.
- The AI agent (Stage 6) will CALL this engine as a tool and generate the explanation around the numbers — but the numbers themselves never come from the LLM.

### Validation results

```
[PASS] Shortage detected
[PASS] PRD-301 is at risk
[PASS] PRD-302 is at risk
[PASS] PRD-303 not flagged (no PRT-104 dependency)  ← correctly excluded
[PASS] CO-501 (Acme) is at risk
[PASS] CO-502 (GlobalTech) is at risk
[PASS] Financial exposure > $20,000 (actual: $42,580)
ALL CHECKS PASSED
```

### Key concept learned: why run order_impact twice?

- First pass → get `daily_consumption_rate` (needs production order data)
- Pass that rate into `inventory.py` → get `shortage_date`
- Second pass → get final risk assessment using real shortage date
- This two-pass design keeps each file focused on one responsibility

---

## Session 6 — Stage 4: Graph & Risk Analysis (Neo4j)

### What we did

- Built 3 files that copy PostgreSQL data into Neo4j as a graph and run relationship queries
- All 4 Cypher queries working and returning correct results

### Files created

- `graph/schema.py` — defines node labels (Supplier, Part, Warehouse etc.) and relationship types (SUPPLIES, REQUIRED_BY, BUILDS etc.) + creates indexes
- `graph/loader.py` — reads PostgreSQL, creates 41 nodes and 71 relationship arrows in Neo4j
- `graph/queries.py` — 4 Cypher query functions wrapped in Python
- `scripts/load_graph.py` — runner script that loads the graph and tests all 4 queries

### How it works

```
PostgreSQL (raw rows)
    ↓  loader.py reads and transforms
Neo4j (nodes + arrows)
    ↓  queries.py navigates
Answers (impact chain, risk scores, spare stock)
```

### What each query does

- **Query 1 — Impact chain:** Start at SUP-005, follow arrows → finds CO-501, CO-502, CO-506 affected ($42,580)
- **Query 2 — Supplier risk ranking:** Scores every supplier by reliability + downstream customer count
- **Query 3 — Dependency concentration:** Which supplier failure causes most damage? Delta Components = $105,280 exposure
- **Query 4 — Spare stock check:** Is there PRT-104 in another warehouse? WH-02 Dallas has 20 units for transfer

### Problem encountered & fixed

- `bolt://localhost:7687` failed — Neo4j was bound to IPv4 only (`127.0.0.1`)
- The driver tried IPv6 (`::1`) first → connection refused
- Fix: changed `NEO4J_URI` in `.env` from `bolt://localhost:7687` to `bolt://127.0.0.1:7687`

### Key concept: why Neo4j and PostgreSQL together?

- PostgreSQL = source of truth (all rows, all columns, all math)
- Neo4j = relationship map (lighter copy, just nodes and arrows)
- loader.py copies relationships from PostgreSQL into Neo4j once
- queries.py navigates Neo4j — no JOINs, just arrow-following
- They never talk to each other — both read from PostgreSQL independently

---

## Session 7 — Stage 5: Recovery Planning

### What we did

- Built 4 files that generate, evaluate, cost, rank, and recommend recovery options for a disruption
- Fixed a critical data issue (daily consumption formula + missing alt supplier)
- Final output: **4 recovery options generated, all feasible, ranked #1–4**
- Impact engine re-validated: **all 7 checks passing with updated scenario**

### Files created

- `core/optimization/options.py` — generates 4 types of recovery option (USE_STOCK, TRANSFER, EXPEDITE, ALT_SUPPLIER)
- `core/optimization/constraints.py` — feasibility checker for each option type
- `core/optimization/costs.py` — cost formulas (freight, expedite premium, alt supplier premium)
- `core/optimization/planner.py` — orchestrator: runs all 4 steps, ranks, prints report

### How the 4 files work together

```
generate_all_options()        ← options.py   : What could we do?
    ↓
check_all_constraints()       ← constraints.py: Can we actually do it?
    ↓
calculate_all_costs()         ← costs.py     : What does it cost?
    ↓
score_options() + rank        ← planner.py   : Which is best?
    ↓
print_recovery_report()                       : Human reads and decides
```

### The 4 option types

| Code  | Type         | What it does                                              |
| ----- | ------------ | --------------------------------------------------------- |
| OPT-A | USE_STOCK    | Use current inventory and monitor coverage                |
| OPT-B | TRANSFER     | Move spare stock from another warehouse (WH-02 → WH-01)  |
| OPT-C | EXPEDITE     | Pay air freight to get the delayed shipment faster        |
| OPT-D | ALT_SUPPLIER | Place emergency order with a different qualified supplier |

### Scoring formula

```
score = (cost_score × 40%) + (speed_score × 40%) + (reliability_score × 20%)
```

- Cost score: cheaper = higher score
- Speed score: arrives faster = higher score
- Reliability: for alt supplier options, historical on-time delivery rate

### Final output (EVT-001)

```
Rank #1  OPT-A  Use Available Stock      Score: 99.0  Cost: $0
Rank #2  OPT-B1 Transfer from WH-02      Score: 76.4  Cost: $350
Rank #3  OPT-D1 Buy from Delta Components Score: 24.3  Cost: $1,060
Rank #4  OPT-C1 Expedite SHP-441         Score: 19.0  Cost: $1,250
```

### Problems fixed this session

**Problem 1 — Daily consumption rate was 145/day (wrong):**

- Old formula: total units needed ÷ days until first order starts
- This gave: 145 ÷ 1 = 145 units/day — completely unrealistic
- Fix: spread total consumption over the full production window (today → last order end date)
- New rate: 145 units ÷ 19-day window = 7.6 units/day ✅

**Problem 2 — No OPT-D (alt supplier) appeared:**

- The system looks for past POs from other suppliers as evidence of qualification
- PRT-104 had only ONE supplier (SUP-005) — no alternate existed in the data
- Fix: added PO-442 (SUP-003 Delta Components, 7-day lead, 91% reliability, DELIVERED past order)
- Now OPT-D correctly appears ✅

**Problem 3 — Transfer option (OPT-B) was infeasible:**

- WH-02 only had 20 units, needed 80 → only 14% coverage (below 50% threshold)
- Fix: WH-02 now has 80 units available = 100% coverage for near-term orders ✅

**Problem 4 — Validation checks were outdated:**

- With 95 units total stock, PRD-301 and PRD-302 are now SAFE (covered by current stock)
- PRD-306 is conservatively AT RISK (starts after theoretical shortage date Nov 2)
- Important nuance: inventory.py says "no shortage" (SHP-441 arrives before stock runs out)
  but order_impact.py conservatively flags PRD-306 (doesn't trust the delayed shipment)
- Both views are CORRECT — they answer different questions, and human judgment is needed
- All 7 validation checks now PASS with updated expected values ✅

### Key concept: separation of concerns

Each file does exactly one job:

- `options.py` never asks "is this affordable?" — that's `costs.py`'s job
- `constraints.py` never ranks — that's `planner.py`'s job
- Adding a 5th option type (e.g., USE_SAFETY_STOCK) means adding ONE function to `options.py` only
- Everything else works automatically — open/closed principle in action

### Key concept: why human-in-the-loop?

The system **recommends** OPT-A (monitor, no action) but never **executes** it.
A human must still:

1. Verify that SHP-441 will actually arrive on Oct 30 (it's already been delayed once)
2. Decide whether to trigger the transfer preemptively as backup
3. Approve or reject the recommendation and log the rationale
   This approval workflow is what Stage 6 (the AI agent) will formalize.

---

## Session 8 — Stage 6: Agent & RAG Layer

### What we did

- Built the full AI agent pipeline: 12 new files across `retrieval/`, `tools/`, and `agents/`
- Loaded 12 synthetic documents into ChromaDB (45 searchable chunks)
- Connected all previous stages (3, 4, 5) as callable tools
- Built a LangGraph workflow with 8 nodes and a human approval gate
- Ran the full end-to-end pipeline — decision saved to PostgreSQL (Decision ID: 1)

### Files created

**retrieval/ (the filing cabinet):**

- `retrieval/documents.py` — 12 synthetic documents: 5 supplier contracts, 3 policies, 3 past decisions, 1 runbook
- `retrieval/embedder.py` — converts documents to vectors, saves to ChromaDB (run once like generate_data.py)
- `retrieval/retriever.py` — semantic search: given a question, returns relevant chunks

**tools/ (the agent's hands — wrappers around stages 3, 4, 5):**

- `tools/impact_tool.py` — wraps Stage 3 engine, returns clean dict
- `tools/planning_tool.py` — wraps Stage 5 planner, returns ranked options dict
- `tools/graph_tool.py` — wraps Stage 4 Neo4j queries, returns impact chain text
- `tools/retrieval_tool.py` — wraps ChromaDB retriever, returns document evidence
- `tools/audit_tool.py` — saves human decisions to PostgreSQL decision_log table

**agents/ (the brain):**

- `agents/state.py` — AgentState TypedDict: 20 fields carried through all nodes
- `agents/nodes.py` — 8 node functions, one per workflow step
- `agents/workflow.py` — LangGraph pipeline connecting all nodes
- `agents/runner.py` — entry point: `uv run python agents/runner.py`

**database:**

- `core/models.py` — added `DecisionLog` table (TABLE 11) to store all human decisions

### The 8-step pipeline (confirmed working)

```
Step 1: validate_event      -> EVT-001 found, OPEN, part=PRT-104, supplier=SUP-005
Step 2: run_impact          -> 95 units stock, 11.8 days coverage, $20,300 exposure
Step 3: run_planning        -> 4 options ranked, OPT-A recommended (score 99.0)
Step 4: fetch_graph         -> Neo4j offline, continued gracefully
Step 5: fetch_documents     -> 4 sources retrieved from ChromaDB
Step 6: generate_explanation-> Gemini 503 (high demand), fallback summary used
Step 7: await_approval      -> Sarah Chen approved OPT-A
Step 8: save_decision       -> Decision ID 1 saved to PostgreSQL
```

### Key concepts learned this session

**What is RAG (Retrieval Augmented Generation)?**
The AI doesn't memorize contracts. Instead:

1. At setup: documents are converted to vectors (numbers) and stored in ChromaDB
2. At query time: the question is converted to a vector, ChromaDB finds the nearest document vectors
3. Those matching documents are given to Gemini as context in its prompt
4. Gemini reads them and cites them in its explanation

This means the AI can "know" about documents it was never trained on.
It also means if you update a contract, just reload ChromaDB — no AI retraining needed.

**What is a LangGraph node?**
Each node is a Python function that takes the state dict and returns updated fields.
LangGraph runs them in order, merging updates back into the state between each step.
The state is like a shared notepad — every node reads from it and writes to it.

**What is human-in-the-loop?**
The workflow PAUSES at Step 7 and waits for a real person to type their decision.
The AI never executes any action. It only recommends.
The human's name, choice, and reason are permanently saved to the audit log.
This is what makes the system "explainable" — every decision is traceable to a person.

### Problems encountered & fixed

**Problem 1 — Wrong function names for Neo4j queries:**
graph_tool.py called `query_impact_chain()` but the function is named `get_impact_chain()`.
Fixed by checking actual function names with `dir(graph.queries)`.

**Problem 2 — graph functions don't take a driver argument:**
The Stage 4 queries manage their own driver connection internally.
Fixed by removing the `driver` parameter from calls.

**Problem 3 — Unicode arrows in Windows terminal:**
`→` character caused UnicodeEncodeError on Windows CP1252 encoding.
Fixed by replacing with `:` in print statements.

**Problem 4 — Gemini 503 (temporary high demand):**
Not a code bug — free tier Gemini has occasional high-demand periods.
Handled gracefully: fallback manual summary is generated when Gemini is unavailable.
The pipeline continues to completion regardless.

---

## Session 9 — Stage 7: API & UI

### What we did

- Moved the human approval out of the AI workflow, so the workflow now ends after the explanation step
- Built a FastAPI backend and a Streamlit UI on top of the existing engines
- Wrote 16 automated tests (all passing)
- Set up git (the project now has more commits; see Session 10)
- Fixed a real bug: results changed from day to day because the code read the computer clock
- Investigated Gemini timeouts (504/503 errors)

Status: **mostly done**. The what-if simulator was dropped by decision and will not be built.

### Why approval moved out of the workflow

In Session 8, the workflow paused at Step 7 and waited for someone to type in the terminal. That does not work behind a web page: a browser cannot "pause" a Python script.

New design:

- `agents/runner.py` has `run_analysis()`. It takes no input and runs Steps 1 to 6, then returns the recommendation.
- `agents/decision.py` has `submit_decision()`. It is a separate function the UI calls when a person clicks Approve or Reject.
- Approval is strict. A real yes/no is required, a name and a rationale are required, and the chosen option must be feasible. Empty input no longer counts as "yes".

This keeps the rule "AI recommends, a human decides, the system never executes".

### Files created or changed

**api/ (the backend):**

- `api/main.py` — FastAPI app with endpoints: `/health`, `/events`, `/events/{id}`, `POST /events/{id}/analyze`, `POST /events/{id}/decision`, `/decisions`, `/inventory/{part_id}`
- `api/schemas.py` — Pydantic models that define what each request and response looks like

**app/ (the frontend):**

- `app/main.py` — Streamlit UI with 6 tabs: Impact, Recovery options, Impact chain (graph), Evidence, AI explanation, Decision (form plus audit log)

**agents/:**

- `agents/decision.py` (new) — `submit_decision()`
- `agents/runner.py` (rewritten) — `run_analysis()` and a command-line entry point
- `agents/workflow.py`, `agents/nodes.py`, `agents/state.py` — approval and save nodes removed; decision fields removed from the state

**core/:**

- `core/clock.py` (new) — the single "as of" date for all calculations (see the bug below)

**tests/:**

- `tests/integration/test_api.py` — 15 tests. Gemini is faked and the audit-log write is captured, so tests never touch the real decision log.
- `tests/unit/test_ui_rendering.py` — 1 regression test

### How the pieces connect

```
Streamlit UI  ->  FastAPI  ->  tools/  ->  core engines (PostgreSQL)
 (browser)       (api/main.py)           + Neo4j graph + ChromaDB + Gemini
```

The decision endpoint does not trust the numbers sent by the browser. It recomputes impact and planning on the server before saving.

### What we verified, and what we did not

Verified:

- You opened the UI in a browser and every tab worked, including the real graph data, the Evidence tab, and a saved Approve (decision 2).
- All 16 tests pass.
- The engine's own 7-point self-check passes.

Not verified or not done:

- Only one scenario exists (EVT-001), so the UI has never been tried on a second event.
- The Gemini explanation works only some of the time (see below).
- The what-if simulator (scenario comparison) was dropped by decision.

### Bugs found and fixed

**Bug 1 — `$` signs turned into maths:**
Streamlit treats text between two `$` signs as a LaTeX formula, so "$20,300 ... $4,800" showed up garbled.
Fix: an `md()` helper escapes the dollar signs, plus a regression test.

**Bug 2 — Numbers drifted from day to day (the important one):**
About ten places in the engine, planner and tools asked the computer clock "what is today?". The coverage figure moved from 12.5 to 11.1 to 10.5 days with no change to the data. The engine's own self-check started failing ("expected 12+ days, got 10.5"). This broke the design rule "same input, same output".
Why it happens: `order_impact.py` spreads a fixed amount of demand over "today until the last order ends". A later "today" gives a shorter window and a higher daily use.
Fix: `core/clock.py` returns the event's `detected_at` date (Oct 20). Every calculation now receives that date as an input. Coverage is now a stable 13.1 days, and the shortage date is Nov 2.
Learned: if a result depends on "now", it is not deterministic. Pass time in as an input.
Two kinds of clock reads remain on purpose: the audit log timestamp and the database `created_at` defaults. Those record when something really happened.

**Bug 3 — Graph tab and Impact tab showed different totals:**
Graph tab: $42,580 (all customer orders that depend on the part). Impact tab: $20,300 (only the orders actually at risk).
Both are correct, since they answer different questions. We added a caption to the graph tab that explains this.

**Problem 4 — Neo4j was out of date:**
Neo4j showed 20 units for WH-02 while PostgreSQL had 80. The graph is a copy and does not update itself.
Fix: rerun `scripts/load_graph.py` whenever the data changes.

### Gemini timeouts (honest status)

- A call that works takes about 14 seconds.
- Many calls fail with 503 (busy) or 504 (Google gave up after about 2 minutes). In one test: two calls hit 504 after 119 seconds, then the third succeeded in 14 seconds.
- So the 504 comes from Google's side. It is not caused by our code.
- We added a 20-second limit per attempt and up to 3 attempts in `agents/nodes.py`. If all fail, the fallback summary is used and the pipeline still finishes.
- The 20-second limit is only 6 seconds above a normal success, and we have not re-measured it. Trying another model is still an open question.

### Environment notes

- The project lives inside OneDrive, which makes disk reads and model loading slow. Embedding model load took 30 to 110 seconds. API start-up took up to 6 minutes once. The test suite takes about 1 to 3 minutes.
- Neo4j is only up when you start it in Neo4j Desktop.
- `keys.md`, `understand.md`, `.env` and `*.log` are git-ignored because they hold secrets or a chat export.

### Key concepts learned this session

**Why split an API from a UI?**
The UI only shows things and collects clicks. The API owns the rules. If someone replaced the UI, or called the API directly, the rules (strict approval, recomputing on the server) would still apply.

**Why fake Gemini in tests?**
A test must give the same answer every time and must not cost anything. A fake Gemini returns a fixed reply, so tests check our code and not Google's mood. The same goes for the audit log: a test must never write into the real one.

**Determinism means controlling time too.**
Same data in, same answer out only holds if the date is also an input.

### Still to do for Stage 7

- [X] What-if simulator: dropped by decision, not building it
- [ ] Test the UI on more than one event
- [X] Gemini 504s: switched model from gemini-3.8-flash (overloaded: 503/504/429 in probes) to gemini-3.5-flash-lite (4/4 OK, ~2.5s). One real UI run succeeded; not proof they are gone for good
- [X] Restart uvicorn: done by the user, UI now shows 13.1 days coverage

---

## Session 10 - Stage 8: Evaluation, Hardening, Release docs

### What we did

- Switched the Gemini model to `gemini-3.5-flash-lite` after the old one kept failing with 503/504
- Added a second scenario, EVT-002 (14-day delay on PRT-112): a real shortage
- Restyled the UI (light theme, "stock runway" timeline, option cards) and moved the CSS into `app/style.css`
- Built an evaluation harness with hand-derived labels and a naive baseline
- **The evaluation found a real bug in the engine, which we fixed**
- Added structured JSON logging with request ids, and input validation
- Wrote Docker files (never run) and the README and architecture docs

### The bug the evaluation found

On EVT-001 the engine said "PRD-306 is at risk, $20,300 exposure". The labels, worked out by hand, said no order is at risk. Why: the engine knew stock would run out on Nov 2 and PRD-306 starts Nov 4, but it ignored that shipment SHP-441 (200 units) lands on Oct 30, before PRD-306 starts.

Fix: when going through orders by start date, add every shipment that has arrived by then to the stock pool.

Lessons:
- A comment in the code called this flag "intentional and conservative". It was a bug that had been explained away. Always ask what a comment is justifying.
- Labels must come from a different method than the code being tested. We used hand calculation plus a separate day-by-day simulation.
- One of my own first labels was wrong (I forgot that expediting is also infeasible on EVT-002). Labels can be wrong too; the disagreement is the signal to investigate, in both directions.
- The scorecard before and after: order precision 50% to 100%, mean exposure error $10,150 to $0.

### Results (2 synthetic cases, deterministic parts only)

| Metric | System | Naive baseline |
|---|---|---|
| Shortage verdict correct | 100% | 50% |
| At-risk order precision / recall | 100% / 100% | 17% / 100% |
| Mean exposure error | $0 | $35,265 |
| Stock-out date error | 1 day | n/a |
| Recommended option correct | 100% | n/a |
| Document Recall@1 / @3 | 100% / 100% | n/a |

Caveats: two cases is too few to say "accurate". `--with-llm` was later run once (2 cases): 100% completed, all $ amounts grounded, but hand-reading found the AI wrongly says the Bosch order prevents the EVT-002 shortage (it arrives after stock-out) and shows "0 units" / "Rank #0" quirks from the planner. Only 2 samples, automatic checks only. The 1-day date gap is a day-counting convention difference we did not resolve.

### The first `--with-llm` run (full agent, real Gemini)

Ran the whole agent on both cases. Two kinds of result:

**Automatic checks (2 cases):** both runs completed with real Gemini text (not the fallback). Every dollar figure in the text was found in the engine numbers. Both texts named the recommended option and cited a source document. Mean time 11.8 s per case. These checks do NOT judge writing quality, and 2 samples is very few.

**Reading the text by hand found 3 problems the checks could not see:**
1. EVT-002: the AI says buying from Bosch "prevents the shortage". Not true. Stock runs out Nov 3, Bosch arrives about Nov 6, so a gap of about 3 days remains. The AI copied this from the planner, which calls the option "feasible".
2. EVT-001: the AI says OPT-B1 transfers "0 units". That comes from the planner output.
3. EVT-002: the AI prints "Rank #0" for an infeasible option. Also from the planner output.

Lesson: the AI added no new wrong numbers. It repeats the planner's flaws. So the fix belongs in the planner first, then the prompt.

### Decisions discussed after the run (PLANNED, NOT YET BUILT)

**Late supplier (Bosch on EVT-002): mark it "partial", not infeasible.**
- If it were infeasible, EVT-002 would have no feasible option and the planner would hide the best action available.
- Bosch still helps: the gap shrinks from about 15 days to about 3.
- Plan: add a `fully_closes_gap` flag and a `residual_gap_days` figure to each option. Keep OPT-D1 recommended but label it "Partial: gap shortens from about 15 days to about 3". Tell the AI prompt never to say "prevents" or "bridges" when the gap is not fully closed.
- The EVT-002 label in `cases.json` would change from "feasible" to "partial, about 3 days left". This must be justified by reasoning (the dates), not by copying the engine output.

**Stock allocation: keep first-come-first-served by planned start date, but show it.**
- Reason to keep: simple, easy to explain, fits the "explainable" goal.
- Known weakness: an early low-value order can use up stock a later high-value order needs. Priority by order value or penalty would fix that, but it is a business rule nobody has validated.
- Plan: print "Stock allocated in order of planned start date" as a visible assumption in each result (UI and AI text). This also closes the partial "every result includes assumptions" item.

Status: both are agreed in principle and written down here. Neither is coded yet.

### Logging and validation

- `core/logging_config.py`: one JSON line per event, with a request id that also comes back in the `X-Request-ID` header
- Ids in URLs are checked (letters, digits, dash, underscore, max 20), decision fields have length limits, and a crash returns "Internal error, request id X" instead of a stack trace
- 6 new tests. Total: 32 passing.

### Docker: attempted, not working

Wrote `Dockerfile`, `docker-compose.yml` and `scripts/docker_seed.py`. Docker Desktop could not be installed: the WSL install hung for 5+ minutes with no progress. We cancelled it. So the Docker files are **never built or run**. Only checked that the YAML parses and the script compiles.

### Other things found

- The data generator's printed notes still said "PRD-306 is AT RISK" after the fix. Corrected.
- A suspected contract inconsistency (3% vs 10% for 8-14 days) turned out to be two different suppliers. Not a bug.
- The what-if simulator stays dropped.

### Still open

- First-come-first-served stock allocation: decided to keep it and show it as an assumption (not coded yet)
- The alternate supplier for EVT-002 arrives after the stock-out but is still called feasible: decided to mark it "partial" with a residual gap (not coded yet). The AI text is wrong on this point until then
- No from-scratch install test, no Docker test, `--with-llm` run only once on 2 cases
- Stage 1 leftovers (user stories) not written