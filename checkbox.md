# SupplyChain Orchestrator — Project Progress Tracker

> An Explainable Agentic AI Platform for Supply Chain Risk and Recovery
> Last updated: Session 8 — Stage 6 Agent & RAG Layer complete

---

## 🗺️ Project Stages Overview

| Stage | Name                        | Status            |
| ----- | --------------------------- | ----------------- |
| 0     | Environment Setup           | ✅ Done          |
| 1     | Requirements & Design       | 🔄 Partially Done |
| 2     | Dataset & Data Model        | ✅ Done           |
| 3     | Deterministic Impact Engine | ✅ Done           |
| 4     | Graph & Risk Analysis       | ✅ Done           |
| 5     | Recovery Planning           | ✅ Done           |
| 6     | Agent & RAG Layer           | ✅ Done           |
| 7     | API & UI                    | 🔄 Mostly Done    |
| 8     | Evaluation & Hardening      | ⬜ Not Started    |
| 9     | Portfolio Release           | ⬜ Not Started    |

---

## ✅ Completed

- [X] Read and understood project plan document (`SupplyChain_Sentinel_Project_Plan.docx`)
- [X] Finalized full tech stack decisions
- [X] Created `Progress.md` (learning journal) and `checkbox.md` (this file) tracker files
- [X] Python 3.11.9 confirmed installed
- [X] uv 0.12.17 confirmed installed
- [X] PostgreSQL 16.15 installed, service running, `supplychain` database created
- [X] Neo4j Desktop 2.2.1 installed, `supplychain` instance running (v2026.09.0)
- [X] Gemini 3.8 Flash API key obtained and verified working
- [X] All Python connections verified (PostgreSQL ✅, Neo4j ✅, Gemini ✅)
- [X] Full project folder structure created
- [X] `pyproject.toml` created with all 184 dependencies
- [X] `core/config.py` created (central config loader)
- [X] `.env.example` created (safe template for secrets)
- [X] `.gitignore` created (protects secrets from being committed)
- [X] `uv sync` completed — virtual environment ready

---

## 🔄 Stage 1 — Requirements & Design (Partially Done)

- [X] Set up project repository structure as per plan
- [ ] Define user stories for each role (planner, procurement, production, inventory, ops manager)
- [X] Define all disruption event types — defined as DisruptionType enum in core/models.py (supplier_delay, quality_hold, demand_spike, inventory_shortage, production_stoppage, logistics_issue)
- [X] Define assumptions — synthetic data only, no live ERP, no real purchase orders (documented in README + code docstrings)
- [ ] Finalize system architecture diagram — planned for Stage 9 (docs/ folder)
- [X] Define acceptance criteria for MVP — implemented as validate_results() in core/impact_analysis/engine.py (7 named checks with pass/fail)

---

## ✅ Stage 2 — Dataset & Data Model (Complete)

- [X] Design relational data schema (PostgreSQL tables)
- [X] Define entities: Suppliers, Parts, Inventory, BOM, Purchase Orders, Production Orders, Customer Orders, Shipments, Warehouses
- [X] Write scripts/init_db.py — 10 tables created in PostgreSQL
- [X] Write scripts/generate_data.py — synthetic data generator with --reset / --seed / --scenario flags
- [X] Inject known disruption scenario (SUP-005 delayed PRT-104 by 4 days on PO-441)
- [X] Validate data — all 10 tables populated with correct row counts
- [X] Data loaded into PostgreSQL (109 total rows across all tables)

---

## ✅ Stage 3 — Deterministic Impact Engine (Complete)

- [X] core/impact_analysis/inventory.py — coverage calculator + shortage date
- [X] core/impact_analysis/bom_tracer.py — BOM traversal (component → products)
- [X] core/impact_analysis/order_impact.py — affected production + customer orders
- [X] core/impact_analysis/engine.py — full orchestrator with report + validation
- [X] All 7 validation checks passed against known test scenario
- [X] Correctly identified PRD-301, PRD-302 at risk; PRD-303 correctly excluded
- [X] Correctly identified CO-501 (Acme), CO-502 (GlobalTech) at risk
- [X] Total financial exposure calculated: $42,580

---

## ✅ Stage 4 — Graph & Risk Analysis (Complete)

- [X] graph/schema.py — node labels, relationship types, index creation
- [X] graph/loader.py — copies PostgreSQL data into Neo4j (41 nodes, 71 relationships)
- [X] graph/queries.py — 4 Cypher queries for impact chain, risk ranking, dependency, spare stock
- [X] scripts/load_graph.py — runner script, all 4 queries verified
- [X] Fixed Neo4j connection (localhost IPv6 vs IPv4 — changed URI to 127.0.0.1)
- [X] Query 1: Impact chain SUP-005 → CO-501 ($11,600), CO-502 ($10,680), CO-506 ($20,300)
- [X] Query 2: Supplier risk ranking working
- [X] Query 3: Dependency concentration — Delta Components $105,280 exposure
- [X] Query 4: Spare stock — WH-02 Dallas has 20 units PRT-104 for transfer

---

## ✅ Stage 5 — Recovery Planning (Complete)

- [X] core/optimization/options.py — 4 recovery option generators (USE_STOCK, TRANSFER, EXPEDITE, ALT_SUPPLIER)
- [X] core/optimization/constraints.py — feasibility checker for each option type with threshold constants
- [X] core/optimization/costs.py — cost formulas (freight, air premium, handling, alt supplier fee)
- [X] core/optimization/planner.py — full orchestrator: generate → check → cost → score → rank → report
- [X] All 4 options generated for EVT-001 (OPT-A, OPT-B1, OPT-C1, OPT-D1)
- [X] All 4 options feasible — correctly ranked by weighted score (cost 40% + speed 40% + reliability 20%)
- [X] OPT-A (Use Stock) recommended as #1 with score 99.0/100 — $0 incremental cost
- [X] Fixed daily consumption formula (spread over full production window, not days-to-first-order)
- [X] Added PO-442 to give SUP-003 alternate supplier history for PRT-104 → OPT-D now appears
- [X] Increased WH-02 stock to 80 units → OPT-B1 transfer option is now feasible
- [X] Impact engine revalidated: all 7 checks passing with updated scenario expectations

---

## ✅ Stage 6 — Agent & RAG Layer (Complete)

- [x] retrieval/documents.py — 12 synthetic documents (5 contracts, 3 policies, 3 past decisions, 1 runbook)
- [x] retrieval/embedder.py — loads documents into ChromaDB (45 chunks, all-MiniLM-L6-v2 model)
- [x] retrieval/retriever.py — semantic search with category/supplier filters
- [x] tools/impact_tool.py — clean wrapper for Stage 3 impact engine
- [x] tools/planning_tool.py — clean wrapper for Stage 5 recovery planner
- [x] tools/graph_tool.py — clean wrapper for Stage 4 Neo4j queries
- [x] tools/retrieval_tool.py — clean wrapper for ChromaDB retriever
- [x] tools/audit_tool.py — saves human decisions to PostgreSQL decision_log table
- [x] core/models.py — added DecisionLog table (TABLE 11), created in PostgreSQL
- [x] agents/state.py — AgentState TypedDict with all 20 fields
- [x] agents/nodes.py — 8 node functions (validate, impact, planning, graph, docs, explain, approve, save)
- [x] agents/workflow.py — LangGraph pipeline with conditional routing after validation
- [x] agents/runner.py — entry point, full end-to-end run tested
- [x] Full pipeline ran: all 8 steps completed, decision saved to DB (Decision ID: 1)
- [x] Gemini 503 handled gracefully with fallback summary (temporary high demand)
- [x] Neo4j offline handled gracefully (continues without graph data)

---

## 🔄 Stage 7 — API & UI (Mostly Done)

- [x] Split approval out of the LangGraph workflow: run_analysis() (no input) + submit_decision() in agents/decision.py
- [x] Approval is explicit: no default "yes", name + rationale required, option must be feasible
- [x] FastAPI endpoints: /health, /events, /events/{id}, /events/{id}/analyze, /events/{id}/decision, /decisions, /inventory/{part_id}
- [x] 15 integration tests passing (Gemini faked, audit log write captured -- real DB not polluted)
- [x] Streamlit UI (app/main.py): impact, options, graph, evidence, AI explanation, decision form, audit log
- [x] UI -> API -> core engine connected; UI verified with Streamlit AppTest against live API
- [x] Fixed date drift: all calculations now use one "as of" date (the event's detected_at, core/clock.py) instead of the live clock. Engine self-check passes again (13.1 days coverage); 16 tests pass

- [x] git repo initialised (keys.md and understand.md are git-ignored: they contain secrets / chat export)
- [-] Scenario comparison view (what-if simulator) -- dropped by the user's decision, will not be built
- [ ] Validate UI with more than one scenario -- only EVT-001 exists in the data
- [ ] Verify graph tab + real Gemini explanation in the UI (Neo4j was offline and Gemini returned 503 during testing)

---
## 🔲 Stage 8 — Evaluation & Hardening

- [ ] Build evaluation harness with labeled test cases
- [ ] Implement impact tracing metrics (precision, recall)
- [ ] Implement shortage estimation metrics (date error, calibration)
- [ ] Implement RAG quality metrics (Recall@k, evidence coverage)
- [ ] Implement agent reliability metrics (task success, tool error rate, latency)
- [ ] Compare results against simple baseline
- [ ] Add structured logging throughout
- [ ] Add error handling and input validation
- [ ] Write documentation (architecture, decisions, setup guide)
- [ ] Dockerize the full stack

---

## 🔲 Stage 9 — Portfolio Release

- [ ] Finalize README with setup instructions
- [ ] Create architecture diagram
- [ ] Record demo
- [ ] Publish evaluation results with honest labeling ("simulated data")
- [ ] Document limitations clearly
- [ ] Push to public repository

---

## 📌 MVP Definition of Done Checklist

- [ ] User can submit a supplier delay event and see affected parts and downstream orders
- [ ] System distinguishes a late shipment from an actual projected shortage
- [ ] Every risk result includes supporting records and stated assumptions
- [ ] At least 3 recovery options can be compared
- [ ] Chosen recommendation passes deterministic feasibility checks
- [ ] User can approve or reject a proposed action and the decision is logged
- [ ] Repeatable evaluation suite compares system with a baseline
- [ ] Project runs from documented setup instructions using synthetic data

---

## 🧰 Final Tech Stack

| Layer           | Technology            | Status       |
| --------------- | --------------------- | ------------ |
| Language        | Python 3.11.9         | ✅ Ready     |
| Package Manager | uv 0.12.17            | ✅ Ready     |
| UI              | Streamlit             | ✅ Installed |
| API             | FastAPI               | ✅ Installed |
| Relational DB   | PostgreSQL 16.15      | ✅ Running   |
| Graph DB        | Neo4j 2026.09.0       | ✅ Running   |
| Vector Store    | ChromaDB              | ✅ Installed |
| LLM             | Gemini 3.8 Flash      | ✅ Verified  |
| ML              | scikit-learn          | ✅ Installed |
| Optimization    | OR-Tools              | ✅ Installed |
| Agent           | LangGraph + LangChain | ✅ Installed |
| Containers      | Docker                | ⬜ Later     |
