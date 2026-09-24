"""Jev's runtime helper retains normal host browser permission routing."""

from types import SimpleNamespace

import pytest

from jiuwenswarm.agents.harness.common.rails.permissions.auto_decision import deterministic_domain_route
from jiuwenswarm.agents.harness.common.rails.permissions.tool_decision_facts import build_tool_decision_facts


def facts(name, args, root):
    return build_tool_decision_facts(name, args, workspace_root=root, original_args_were_valid_object=True)


@pytest.mark.parametrize("url", ["https://example.test/", "https://127.0.0.1/", "http://example.test/"])
def test_jev_navigation_has_the_same_network_and_review_boundaries_as_native_navigation(tmp_path, url):
    profile = SimpleNamespace(network_guard_enforced=True)
    native = deterministic_domain_route(facts("browser_navigate", {"url": url}, tmp_path),
                                        original_user_intent=None, browser_runtime_security_profile=profile)
    helper = deterministic_domain_route(facts("browser_page_action", {
        "generation_id": "g1", "op": "navigate", "url": url,
    }, tmp_path), original_user_intent=None, browser_runtime_security_profile=profile)
    assert helper == native
    assert not helper.is_deterministic_allow


def test_bounded_scroll_still_requires_normal_interaction_review(tmp_path):
    route = deterministic_domain_route(facts("browser_page_action", {
        "generation_id": "g1", "op": "scroll", "direction": "down",
    }, tmp_path), original_user_intent=None)
    assert route.reason == "domain_policy_browser_interactive"
    assert route.requires_reviewer and not route.is_deterministic_allow
