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
| LLM | Gemini (free tier; model set in core/config.py) |
| Agent Orchestration | LangGraph + LangChain |
| Optimization | OR-Tools |

## Project Structure

```
supplychain-orchestrator/
â”œâ”€â”€ app/                    # Streamlit UI
â”œâ”€â”€ api/                    # FastAPI routes and schemas
â”œâ”€â”€ core/
â”‚   â”œâ”€â”€ impact_analysis/    # Inventory coverage and dependency impact
â”‚   â”œâ”€â”€ forecasting/        # Demand and risk models
â”‚   â”œâ”€â”€ optimization/       # Recovery planning and constraints
â”‚   â””â”€â”€ rules/              # Deterministic business rules
â”œâ”€â”€ agents/                 # LangGraph workflows and tool routing
â”œâ”€â”€ retrieval/              # Document ingestion, indexing, RAG
â”œâ”€â”€ graph/                  # Neo4j schema and graph queries
â”œâ”€â”€ tools/                  # MCP tools and service adapters
â”œâ”€â”€ data/
â”‚   â”œâ”€â”€ synthetic/          # Generated demo data
â”‚   â””â”€â”€ scenarios/          # Known disruption test cases
â”œâ”€â”€ evaluation/             # Metrics, baselines, scenario tests
â”œâ”€â”€ tests/                  # Unit, integration, and workflow tests
â”œâ”€â”€ docs/                   # Architecture, decisions, diagrams
â”œâ”€â”€ scripts/                # Data generation and local setup
â”œâ”€â”€ pyproject.toml
â”œâ”€â”€ .env.example
â””â”€â”€ README.md
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
# API (terminal 1; first start takes ~30s to load the embedding model)
uv run uvicorn api.main:app --reload

# UI (terminal 2)
uv run streamlit run app/main.py

# Tests
uv run pytest tests
```

## Status
ðŸš§ Under active development â€” prototype stage
