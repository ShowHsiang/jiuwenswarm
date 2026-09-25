"""Summarize sanitized Jev decision logs and explicitly labelled threshold samples.

Example: uv run python scripts/jev_calibrate.py --log browser_agent.log --labels labels.jsonl
Labels: {"decision_id":"jev_...", "correct":true}. Executor success is NOT a correctness label.
No model calls, configuration writes, raw task text or credentials are required.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def read_events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
        for marker in (
            "BROWSER_POLICY",
            "BROWSER_POLICY_REQUEST",
            "BROWSER_POLICY_RESPONSE",
            "BROWSER_POLICY_HTTP_START",
            "BROWSER_POLICY_HTTP_END",
            "BROWSER_POLICY_EXECUTION",
            "BROWSER_POLICY_SHADOW",
            "BROWSER_POLICY_POSTCONDITION",
            "BROWSER_POLICY_DISPATCH",
            "BROWSER_PHASE",
            "BROWSER_EXECUTION",
            "BROWSER_TIMING",
        ):
            tag = f"[{marker}] "
            if tag not in line:
                continue
            try:
                value = json.loads(line.split(tag, 1)[1])
            except ValueError:
                events.append({"event": "PARSE_ERROR", "marker": marker, "line": line_number})
                break
            if isinstance(value, dict):
                events.append({**value, "event": marker})
            else:
                events.append({"event": "PARSE_ERROR", "marker": marker, "line": line_number})
            break
    return events


def summarize(events: list[dict[str, Any]], labels: dict[str, bool] | None = None) -> dict[str, Any]:
    labels = labels or {}
    routes = [event for event in events if event["event"] == "BROWSER_POLICY"]
    outcomes = [event for event in events if event["event"] in {"BROWSER_POLICY", "BROWSER_POLICY_SHADOW"}]
    terminal_by_id = {event["decision_id"]: event for event in outcomes if event.get("decision_id")}
    requests = {
        event["decision_id"]: event
        for event in events
        if event["event"] == "BROWSER_POLICY_REQUEST" and event.get("decision_id")
    }
    responses = {
        event["decision_id"]: event
        for event in events
        if event["event"] == "BROWSER_POLICY_RESPONSE" and event.get("decision_id")
    }
    executions = {
        event["decision_id"]: event
        for event in events
        if event["event"] == "BROWSER_POLICY_EXECUTION" and event.get("decision_id")
    }
    samples = []
    for decision_id, event in responses.items():
        if terminal_by_id.get(decision_id, {}).get("reason") not in {"compiled_action", "uncertain_choice", "shadow"}:
            continue  # Protocol-invalid responses cannot be enabled by a lower confidence threshold.
        confidence, margin, top1 = (event.get(key) for key in ("confidence", "probability_margin", "top1"))
        if type(labels.get(decision_id)) is not bool or not event.get("operation"):
            continue
        if not all(
            type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1
            for value in (confidence, margin, top1)
        ):
            continue
        samples.append(
            {
                "operation": event["operation"],
                "confidence": confidence,
                "margin": margin,
                "top1": top1,
                "correct": labels[decision_id],
            }
        )
    rows = []
    for operation in sorted({sample["operation"] for sample in samples}):
        group = [sample for sample in samples if sample["operation"] == operation]
        for confidence in (0.5, 0.6, 0.65, 0.7, 0.8, 0.9):
            for margin in (0.0, 0.1, 0.2):
                accepted = [s for s in group if s["confidence"] >= confidence and s["margin"] >= margin]
                errors = sum(not sample["correct"] for sample in accepted)
                rows.append(
                    {
                        "operation": operation,
                        "min_confidence": confidence,
                        "min_margin": margin,
                        "labelled": len(group),
                        "accepted": len(accepted),
                        "errors": errors,
                        "coverage": len(accepted) / len(group),
                        "error_rate": errors / len(accepted) if accepted else None,
                        "mean_top1": sum(s["top1"] for s in accepted) / len(accepted) if accepted else None,
                    }
                )
    parse_errors = [event for event in events if event["event"] == "PARSE_ERROR"]
    adopted_ids = {event.get("decision_id") for event in routes if event.get("route") == "jev"}
    integrity = {
        "parse_errors": len(parse_errors),
        "invalid_lines": [{"line": e["line"], "marker": e["marker"]} for e in parse_errors],
        "requests_without_response": sorted(requests.keys() - responses.keys()),
        "adopted_without_execution": sorted(adopted_ids - executions.keys() - {None}),
        "responses_without_request": sorted(responses.keys() - requests.keys()),
    }
    postconditions = [event for event in events if event["event"] == "BROWSER_POLICY_POSTCONDITION"]
    timings = {}
    for event in events:
        value = event.get("elapsed_ms")
        if event["event"] == "BROWSER_TIMING" and type(value) in {int, float} and math.isfinite(value) and value >= 0:
            timings.setdefault(event.get("component", "unknown"), []).append(value)
    timing_summary = {}
    for component, values in timings.items():
        values.sort()
        timing_summary[component] = {
            "count": len(values), "total_ms": round(sum(values), 3),
            "p50_ms": values[(len(values) - 1) // 2], "p95_ms": values[math.ceil(len(values) * 0.95) - 1],
        }
    return {
        "timings_by_component": timing_summary,
        "timing_note": (
            "Components may overlap (guard/verification within tool lifecycle); do not sum into task latency."
        ),
        "log_integrity": integrity,
        "measurement_status": "incomplete" if any(integrity.values()) else "complete",
        "postconditions": dict(Counter(event.get("postcondition") for event in postconditions)),
        "execution_states": dict(
            Counter(event.get("execution_state", "legacy_unspecified") for event in executions.values())
        ),
        "logical_evaluations": len(requests),
        "responses": len(responses),
        "http_attempts": sum(event["event"] == "BROWSER_POLICY_HTTP_START" for event in events),
        "routes": dict(Counter(event.get("route") for event in routes)),
        "reasons": dict(Counter(event.get("reason") for event in routes)),
        "cached_fallbacks": sum(bool(event.get("cached_fallback")) for event in routes),
        "adopted": sum(event.get("route") == "jev" for event in routes),
        "execution_receipts": len(executions),
        "execution_successes": sum(e.get("success") is True for e in executions.values()),
        "jev_total_ms": round(sum(event.get("jev_ms", 0) for event in outcomes), 2),
        "labelled_decisions": len(samples),
        "threshold_comparison": rows,
        "threshold_change_applied": False,
        "calibration_status": "labelled_comparison_only" if samples else "needs_human_labels",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    labels = {}
    if args.labels:
        for line in args.labels.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                item = json.loads(line)
                if not isinstance(item.get("decision_id"), str) or type(item.get("correct")) is not bool:
                    parser.error("Each label needs a string decision_id and a boolean correct.")
                labels[item["decision_id"]] = item["correct"]
    report = json.dumps(summarize(read_events(args.log), labels), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
