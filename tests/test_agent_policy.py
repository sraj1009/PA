"""Unit tests for bee.agent.policy — the regex policy detectors extracted from
bee/agent/loop.py (refactor, 2026-10-18).

The loop only branches on these booleans; these tests pin the detector
behavior and the legacy private re-exports the rest of the tree imports
(reflection.py, pipeline/derive_prefs.py, tests).
"""
from bee.agent import policy


def test_plan_and_code_request_detectors():
    assert policy.wants_plan("make me a roadmap for next week")
    assert policy.wants_plan("give me step-by-step instructions")
    assert policy.wants_plan("planning a trip")
    assert not policy.wants_plan("what is the weather")
    assert not policy.wants_plan(None)

    assert policy.wants_python("compute this with a Python snippet")
    assert not policy.wants_python("compute this")

    assert policy.wants_result("how many primes between 1 and 100")
    assert policy.wants_result("what is 2+2")
    assert not policy.wants_result("write a poem")


def test_fence_and_output_detectors():
    m = policy.first_py_fence("here you go:\n```python\nprint(1 + 1)\n```\ndone")
    assert m and m.group(1).strip() == "print(1 + 1)"
    assert policy.first_py_fence("no code here") is None

    assert policy.prints_output("print(x)")
    assert policy.prints_output("sys.stdout.write('x')")
    assert policy.prints_output("n = int(input())")
    assert not policy.prints_output("x = gcd(a, b)")
    assert "appended by BEE" in policy.VALUE_READOUT


def test_meta_ramble_and_harness_detectors():
    assert policy.is_meta_ramble("It seems that no function calls were provided")
    assert policy.is_meta_ramble("I didn't receive any tool calls")
    assert policy.is_meta_ramble("what action was intended")
    # a real failure report is NOT plumbing talk
    assert not policy.is_meta_ramble("The tool call failed with a timeout.")

    assert policy.narrates_tool_call("I will use a computer_command function call now")
    assert not policy.narrates_tool_call("Done — here is the answer.")

    assert policy.is_harness_plumbing('{"blocked": true}')
    assert policy.is_harness_plumbing('"note": "You already ran this tool call"')
    assert not policy.is_harness_plumbing("The file contains 42 lines.")


def test_tool_surface_question_detector():
    assert policy.asks_about_tools("what tools are available")
    assert policy.asks_about_tools("do you have any tools")
    # an instruction to USE a tool is not a question ABOUT the tool surface
    assert not policy.asks_about_tools("use the planner tool to plan this")


def test_loop_reexports_stay_importable():
    """Compat contract: the historical private names stay on bee.agent.loop."""
    from bee.agent import answer_postprocess, episode_metrics, tool_dispatch
    from bee.agent.loop import (AgentResult, _cloud_up,  # noqa: F401
                                _extract_text_tool_calls, _finish,
                                _grounded_fallback, _META_RAMBLE_RE,
                                _validate_call, run_agent)  # noqa: F401
    assert _META_RAMBLE_RE is policy.META_RAMBLE_RE
    assert _extract_text_tool_calls is tool_dispatch.extract_text_tool_calls
    assert _validate_call is tool_dispatch.validate_call
    assert _finish is episode_metrics.finish
    assert _grounded_fallback is answer_postprocess.grounded_fallback
