# SupplyChain Orchestrator

> An Explainable Agentic AI Platform for Supply Chain Risk and Recovery

## What This Project Does

When a supplier is delayed, this platform:
1. Detects the disruption
2. Traces which parts, production orders, and customer orders are affected
3. Estimates if there's an actual shortage (not just a late shipment)
4. Proposes ranked recovery options (use stock / transfer / expedite / alternate supplier)
5. Explains every recommendation with evidence
6. Asks a human to approve before any action is taken

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11 |
| Package Manager | uv |
| UI | Streamlit |
| API | FastAPI |
| Relational DB | PostgreSQL 16 |
| Graph DB | Neo4j Desktop |
| Vector Store | ChromaDB |
| LLM | Gemini 1.5 Flash (free tier) |
| Agent Orchestration | LangGraph + LangChain |
| Optimization | OR-Tools |

## Project Structure

```
supplychain-orchestrator/
├── app/                    # Streamlit UI
├── api/                    # FastAPI routes and schemas
├── core/
│   ├── impact_analysis/    # Inventory coverage and dependency impact
│   ├── forecasting/        # Demand and risk models
│   ├── optimization/       # Recovery planning and constraints
│   └── rules/              # Deterministic business rules
├── agents/                 # LangGraph workflows and tool routing
├── retrieval/              # Document ingestion, indexing, RAG
├── graph/                  # Neo4j schema and graph queries
├── tools/                  # MCP tools and service adapters
├── data/
│   ├── synthetic/          # Generated demo data
│   └── scenarios/          # Known disruption test cases
├── evaluation/             # Metrics, baselines, scenario tests
├── tests/                  # Unit, integration, and workflow tests
├── docs/                   # Architecture, decisions, diagrams
├── scripts/                # Data generation and local setup
├── pyproject.toml
├── .env.example
└── README.md
```

## Setup Instructions

### 1. Prerequisites
- Python 3.11+
- uv (package manager)
- PostgreSQL 16
- Neo4j Desktop

### 2. Clone and Install
```bash
git clone <repo-url>
cd supplychain-orchestrator
uv sync
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your actual keys and passwords
```

### 4. Run
```bash
# API
uv run uvicorn api.main:app --reload

# UI
uv run streamlit run app/main.py
```

## Status
🚧 Under active development — prototype stage
