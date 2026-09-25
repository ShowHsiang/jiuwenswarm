"""Execution success must not be mistaken for a labelled correct model choice."""

import importlib.util
from pathlib import Path

module_path = Path(__file__).parents[3] / "scripts" / "jev_calibrate.py"
spec = importlib.util.spec_from_file_location("jev_calibrate", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_rejected_choice_is_available_for_calibration_but_needs_a_real_label():
    events = [
        {"event": "BROWSER_POLICY_REQUEST", "decision_id": "jev_a"},
        {
            "event": "BROWSER_POLICY_RESPONSE",
            "decision_id": "jev_a",
            "operation": "click",
            "confidence": 0.6,
            "probability_margin": 0.3,
            "top1": 0.8,
        },
        {"event": "BROWSER_POLICY", "decision_id": "jev_a", "route": "llm", "reason": "uncertain_choice"},
        {"event": "BROWSER_POLICY_EXECUTION", "decision_id": "jev_a", "success": True},
    ]
    result = module.summarize(events)
    assert result["logical_evaluations"] == 1 and result["adopted"] == 0
    assert result["labelled_decisions"] == 0 and not result["threshold_comparison"]
    result = module.summarize(events, {"jev_a": False})
    low = next(row for row in result["threshold_comparison"] if row["min_confidence"] == 0.5 and row["min_margin"] == 0)
    assert low["errors"] == 1 and low["error_rate"] == 1
    high = next(
        row for row in result["threshold_comparison"] if row["min_confidence"] == 0.65 and row["min_margin"] == 0
    )
    assert high["accepted"] == 0 and high["error_rate"] is None
    assert not result["threshold_change_applied"]
    events[2]["reason"] = "invalid_choice_distribution"
    assert module.summarize(events, {"jev_a": True})["labelled_decisions"] == 0


def test_shadow_evaluation_is_not_counted_as_an_additional_model_window():
    events = [
        {"event": "BROWSER_POLICY", "route": "llm", "reason": "shadow_scheduled"},
        {"event": "BROWSER_POLICY_SHADOW", "decision_id": "jev_a", "route": "llm", "reason": "shadow", "jev_ms": 50},
    ]
    report = module.summarize(events)
    assert report["routes"] == {"llm": 1}
    assert report["jev_total_ms"] == 50


def test_corrupt_decimal_lines_are_reported_and_never_silently_dropped(tmp_path):
    path = tmp_path / "sanitized.log"
    path.write_text(
        '[BROWSER_POLICY_REQUEST] {"decision_id":"jev_trace"}\n'
        '[BROWSER_POLICY_RESPONSE] {"decision_id":"jev_trace","probability_margin":0.******}\n'
        '[BROWSER_POLICY] {"decision_id":"jev_trace","route":"jev"}\n', encoding="utf-8"
    )
    report = module.summarize(module.read_events(path))
    assert report["measurement_status"] == "incomplete"
    assert report["log_integrity"]["invalid_lines"] == [{"line": 2, "marker": "BROWSER_POLICY_RESPONSE"}]
    assert report["log_integrity"]["requests_without_response"] == ["jev_trace"]
    assert report["log_integrity"]["adopted_without_execution"] == ["jev_trace"]


def test_execution_success_is_separate_from_business_verification():
    report = module.summarize([
        {"event": "BROWSER_POLICY_EXECUTION", "decision_id": "jev_a", "success": True,
         "execution_state": "acknowledged"},
        {"event": "BROWSER_POLICY_POSTCONDITION", "decision_id": "jev_a", "postcondition": "conditions_unsatisfied"},
    ])
    assert report["execution_successes"] == 1
    assert report["postconditions"] == {"conditions_unsatisfied": 1}
    assert report["labelled_decisions"] == 0


def test_component_timing_totals_do_not_claim_end_to_end_latency():
    report = module.summarize([
        {"event": "BROWSER_TIMING", "component": "observation", "elapsed_ms": 18.123456789012345},
        {"event": "BROWSER_TIMING", "component": "guard", "elapsed_ms": 5},
        {"event": "BROWSER_TIMING", "component": "tool_lifecycle", "elapsed_ms": 50},
    ])
    assert report["timings_by_component"]["observation"]["count"] == 1
    assert report["timings_by_component"]["tool_lifecycle"]["total_ms"] == 50
    assert "do not sum" in report["timing_note"]
