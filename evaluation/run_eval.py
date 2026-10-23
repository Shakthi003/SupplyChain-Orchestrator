"""
evaluation/run_eval.py -- run the labeled cases and print a scorecard.

  python -m evaluation.run_eval            (deterministic parts only)
  python -m evaluation.run_eval --with-llm (also runs the full agent incl. Gemini)

Saves evaluation/results.json. The data is SYNTHETIC: read the numbers as
"the engine agrees with an independent calculation", not as real-world accuracy.
"""

import argparse
import json
import time
from pathlib import Path

from evaluation.baseline import naive_baseline
from evaluation.metrics import (date_error_days, mean, phrase_coverage,
                                precision_recall, recall_at_k)
from retrieval.retriever import get_penalty_clause
from tools.impact_tool import run_impact_analysis_tool
from tools.planning_tool import run_recovery_planning_tool

HERE = Path(__file__).parent


def timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, time.perf_counter() - t0


def evaluate_case(case: dict, tol_days: int, with_llm: bool) -> dict:
    exp = case["expected"]
    eid = case["event_id"]
    row = {"event_id": eid, "latency_s": {}, "tool_errors": 0, "tool_calls": 0}

    # --- Impact tracing + shortage estimation ---------------------------------
    impact, dt = timed(run_impact_analysis_tool, eid)
    row["latency_s"]["impact"] = round(dt, 2)
    row["tool_calls"] += 1
    row["tool_errors"] += bool(impact.get("error"))

    prod = precision_recall([p["order_id"] for p in impact.get("at_risk_prod_orders", [])],
                            exp["at_risk_production_orders"])
    cust = precision_recall([c["order_id"] for c in impact.get("at_risk_cust_orders", [])],
                            exp["at_risk_customer_orders"])
    row["production_orders"] = prod
    row["customer_orders"] = cust
    row["shortage_correct"] = impact.get("has_shortage") == exp["has_shortage"]
    row["exposure_error"] = round(abs(impact.get("total_exposure", 0) - exp["exposure"]), 2)
    row["exposure_correct"] = row["exposure_error"] < 0.01
    # Date error only means something when a stock-out is expected.
    err = date_error_days(impact.get("shortage_date"), exp["stockout_date"]) if exp["has_shortage"] else None
    row["stockout_date_error_days"] = err
    row["stockout_date_within_tolerance"] = None if err is None else err <= tol_days

    # --- Naive baseline --------------------------------------------------------
    base = naive_baseline(impact.get("affected_products", []))
    row["baseline"] = {
        "shortage_correct": base["has_shortage"] == exp["has_shortage"],
        "production_orders": precision_recall(base["production_orders"], exp["at_risk_production_orders"]),
        "customer_orders": precision_recall(base["customer_orders"], exp["at_risk_customer_orders"]),
        "exposure": base["exposure"],
        "exposure_error": round(abs(base["exposure"] - exp["exposure"]), 2),
    }

    # --- Planning ----------------------------------------------------------------
    plan, dt = timed(run_recovery_planning_tool, eid)
    row["latency_s"]["planning"] = round(dt, 2)
    row["tool_calls"] += 1
    row["tool_errors"] += bool(plan.get("error"))
    infeasible = sorted(o["option_id"] for o in plan.get("options", []) if o["status"] != "feasible")
    row["recommended_correct"] = plan.get("recommended_option_id") == exp["recommended_option"]
    row["infeasible_correct"] = infeasible == sorted(exp["infeasible_options"])
    # Options that are feasible but arrive after the stock-out, with their leftover shortage.
    partial = {o["option_id"]: o["residual_gap_days"] for o in plan.get("options", [])
               if o["status"] == "feasible" and not o.get("fully_closes_gap", True)}
    want = exp.get("partial_options", {})
    row["partial_correct"] = (
        sorted(partial) == sorted(want)
        and all(abs(partial[k] - want[k]) <= tol_days for k in want)
    )
    row["partial_options"] = partial
    row["options_generated"] = len(plan.get("options", []))
    row["options_feasible"] = sum(1 for o in plan.get("options", []) if o["status"] == "feasible")

    # --- Retrieval (RAG) -----------------------------------------------------------
    hits, dt = timed(get_penalty_clause, case["supplier_id"], case["delay_days"])
    row["latency_s"]["retrieval"] = round(dt, 2)
    row["tool_calls"] += 1
    ranked = [h["doc_id"] for h in hits]
    row["retrieval"] = {
        "recall_at_1": recall_at_k(ranked, exp["evidence_docs"], 1),
        "recall_at_3": recall_at_k(ranked, exp["evidence_docs"], 3),
        "evidence_coverage": phrase_coverage(" ".join(h["text"] for h in hits), exp["evidence_phrases"]),
        "ranked": ranked,
    }

    # --- Full agent incl. LLM (optional: slow, needs the Gemini key) ------------------
    # Kept out of row["latency_s"] so it does not distort the tool-latency average.
    if with_llm:
        from agents.runner import run_analysis
        state, dt = timed(run_analysis, eid)
        text = state.get("explanation", "") or ""
        row["full_agent_latency_s"] = round(dt, 2)
        row["agent_success"] = bool(state.get("event_valid")) and not text.startswith("[AI explanation unavailable")
        row["explanation_check"] = check_explanation(
            text, state.get("impact_result") or {}, state.get("planning_result") or {}, exp
        )
        row["explanation_text"] = text
    return row


def _numbers_in(obj, out: set) -> set:
    """Every number found anywhere in an engine result (dicts/lists/values)."""
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(round(float(obj), 2))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, out)
    return out


def check_explanation(text: str, impact: dict, plan: dict, exp: dict) -> dict:
    """
    Cheap, honest checks on the LLM text. They do NOT judge writing quality.
      grounded_dollars : every $ amount in the text equals some number the engines produced
      ungrounded       : the $ amounts that do not (may be legitimate derived figures,
                         e.g. a penalty % applied to a PO value -- inspect by hand)
      mentions_recommendation : the recommended option id appears
      cites_evidence   : at least one expected contract phrase / doc id appears
    """
    import re
    if text.startswith("[AI explanation unavailable"):
        return {"skipped": "LLM fallback text, nothing to check"}
    known = _numbers_in(impact, set()) | _numbers_in(plan, set())
    amounts = [float(m.replace(",", "")) for m in re.findall(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)", text)]
    ungrounded = sorted({a for a in amounts if round(a, 2) not in known})
    low = text.lower()
    return {
        "dollar_amounts_found": len(amounts),
        "grounded_dollars": not ungrounded,
        "ungrounded": ungrounded,
        "mentions_recommendation": exp["recommended_option"].lower() in low,
        "cites_evidence": any(p.lower() in low for p in exp["evidence_phrases"] + exp["evidence_docs"]),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    flat = lambda key: [r[key] for r in rows]
    calls = sum(r["tool_calls"] for r in rows)
    return {
        "cases": n,
        "shortage_verdict_accuracy": sum(flat("shortage_correct")) / n,
        "baseline_shortage_verdict_accuracy": sum(r["baseline"]["shortage_correct"] for r in rows) / n,
        "production_order_precision": mean(r["production_orders"]["precision"] for r in rows),
        "production_order_recall": mean(r["production_orders"]["recall"] for r in rows),
        "baseline_production_order_precision": mean(r["baseline"]["production_orders"]["precision"] for r in rows),
        "baseline_production_order_recall": mean(r["baseline"]["production_orders"]["recall"] for r in rows),
        "customer_order_precision": mean(r["customer_orders"]["precision"] for r in rows),
        "customer_order_recall": mean(r["customer_orders"]["recall"] for r in rows),
        "exposure_exact_match_rate": sum(flat("exposure_correct")) / n,
        "mean_exposure_error_usd": mean(flat("exposure_error")),
        "mean_baseline_exposure_error_usd": mean(r["baseline"]["exposure_error"] for r in rows),
        "mean_stockout_date_error_days": mean(flat("stockout_date_error_days")),
        "recommended_option_accuracy": sum(flat("recommended_correct")) / n,
        "infeasible_option_accuracy": sum(flat("infeasible_correct")) / n,
        "partial_option_accuracy": sum(flat("partial_correct")) / n,
        "retrieval_recall_at_1": mean(r["retrieval"]["recall_at_1"] for r in rows),
        "retrieval_recall_at_3": mean(r["retrieval"]["recall_at_3"] for r in rows),
        "evidence_coverage": mean(r["retrieval"]["evidence_coverage"] for r in rows),
        "tool_error_rate": sum(r["tool_errors"] for r in rows) / calls,
        "mean_tool_latency_s": mean(v for r in rows for v in r["latency_s"].values()),
        **_llm_summary(rows),
    }


def _llm_summary(rows: list[dict]) -> dict:
    """Only present when the run used --with-llm."""
    llm = [r for r in rows if "agent_success" in r]
    if not llm:
        return {}
    checked = [r["explanation_check"] for r in llm if "skipped" not in r["explanation_check"]]
    return {
        "llm_runs": len(llm),
        "llm_success_rate": sum(r["agent_success"] for r in llm) / len(llm),
        "llm_checked_explanations": len(checked),
        "llm_grounded_dollars_rate": (sum(c["grounded_dollars"] for c in checked) / len(checked)) if checked else None,
        "llm_mentions_recommendation_rate": (sum(c["mentions_recommendation"] for c in checked) / len(checked)) if checked else None,
        "llm_cites_evidence_rate": (sum(c["cites_evidence"] for c in checked) / len(checked)) if checked else None,
        "llm_mean_full_agent_latency_s": mean(r["full_agent_latency_s"] for r in llm),
    }


def print_report(summary: dict, rows: list[dict]) -> None:
    pct = lambda x: "n/a" if x is None else f"{x * 100:.0f}%"
    print("\n=== Evaluation (SYNTHETIC data, %d labeled cases) ===" % summary["cases"])
    print(f"{'Metric':<42}{'System':>10}{'Baseline':>10}")
    print(f"{'Shortage verdict accuracy':<42}{pct(summary['shortage_verdict_accuracy']):>10}{pct(summary['baseline_shortage_verdict_accuracy']):>10}")
    print(f"{'At-risk production orders: precision':<42}{pct(summary['production_order_precision']):>10}{pct(summary['baseline_production_order_precision']):>10}")
    print(f"{'At-risk production orders: recall':<42}{pct(summary['production_order_recall']):>10}{pct(summary['baseline_production_order_recall']):>10}")
    print(f"{'Mean exposure error (USD)':<42}{summary['mean_exposure_error_usd']:>10,.0f}{summary['mean_baseline_exposure_error_usd']:>10,.0f}")
    err = summary["mean_stockout_date_error_days"]
    print(f"{'Stock-out date error (days, shortage cases)':<42}{('n/a' if err is None else f'{err:.1f}'):>10}")
    print(f"{'Recommended option correct':<42}{pct(summary['recommended_option_accuracy']):>10}")
    print(f"{'Infeasible options identified':<42}{pct(summary['infeasible_option_accuracy']):>10}")
    print(f"{'Partial (late) options identified':<42}{pct(summary['partial_option_accuracy']):>10}")
    print(f"{'Retrieval Recall@1 / Recall@3':<42}{pct(summary['retrieval_recall_at_1']):>10}{pct(summary['retrieval_recall_at_3']):>10}")
    print(f"{'Evidence coverage (required facts found)':<42}{pct(summary['evidence_coverage']):>10}")
    print(f"{'Tool error rate':<42}{pct(summary['tool_error_rate']):>10}")
    print(f"{'Mean tool latency (s)':<42}{summary['mean_tool_latency_s']:>10.2f}")
    print()
    for r in rows:
        bits = []
        if r["production_orders"]["fp"] or r["production_orders"]["fn"]:
            bits.append(f"prod FP={r['production_orders']['fp']} FN={r['production_orders']['fn']}")
        if r["stockout_date_error_days"]:
            bits.append(f"stock-out date off by {r['stockout_date_error_days']}d")
        if r["options_feasible"] < 3:
            bits.append(f"only {r['options_feasible']} feasible option(s) of {r['options_generated']}")
        print(f"  {r['event_id']}: " + ("; ".join(bits) if bits else "all checks matched"))
    if "llm_runs" in summary:
        print("--- Full agent (Gemini) ---")
        print(f"{'Agent runs completed':<42}{pct(summary['llm_success_rate']):>10}  ({summary['llm_runs']} runs)")
        print(f"{'Explanations checked (not fallback)':<42}{summary['llm_checked_explanations']:>10}")
        print(f"{'Every $ amount found in engine numbers':<42}{pct(summary['llm_grounded_dollars_rate']):>10}")
        print(f"{'Mentions recommended option':<42}{pct(summary['llm_mentions_recommendation_rate']):>10}")
        print(f"{'Cites a source document':<42}{pct(summary['llm_cites_evidence_rate']):>10}")
        print(f"{'Mean full-agent time (s)':<42}{summary['llm_mean_full_agent_latency_s']:>10.1f}")
        print("(Automatic checks only. They do NOT judge writing quality.)")
        for r in rows:
            chk = r.get("explanation_check", {})
            if "skipped" in chk:
                print(f"  {r['event_id']}: explanation skipped -> {chk['skipped']}")
            elif chk.get("ungrounded"):
                print(f"  {r['event_id']}: $ amounts NOT in engine numbers (check by hand): {chk['ungrounded']}")
        print()



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true", help="also run the full agent (calls Gemini)")
    args = ap.parse_args()

    spec = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    tol = spec.get("stockout_tolerance_days", 1)
    rows = [evaluate_case(c, tol, args.with_llm) for c in spec["cases"]]
    summary = summarize(rows)
    out = {"data": "synthetic", "summary": summary, "cases": rows}
    (HERE / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print_report(summary, rows)
    print("\nSaved evaluation/results.json")


if __name__ == "__main__":
    main()
