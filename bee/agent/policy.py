"""Deterministic regex policy detectors for agent replies and task wording.

These patterns were inline in `bee.agent.loop`. They are pure text
classifiers — no state, no side effects — and every comment (with the live
eval evidence behind it) travels with the pattern it explains. The loop
branches on the booleans; unit-tested in tests/test_agent_policy.py.
"""
from __future__ import annotations

import re

# The model narrates a call instead of making it ("I will use a ... function
# call to ..."). One bounded nudge converts it into either a call or an answer.
TOOL_INTENT_RE = re.compile(
    r"\b(?:i\s+will|i'?ll|let\s+me|i\s+am\s+going\s+to|we\s+shall)\b"
    r"[^.\n]{0,60}\b(?:function|tool)\s*call", re.I)

# A 3B model that loses the plot answers the SYSTEM PROMPT instead of the user:
# "It seems there was an error… no function calls were provided for execution.
# The available functions are: …". That text is never an acceptable reply.
# …but a user who genuinely asks about the tool surface must get that answer.
# The exemption is about the QUESTION, not about the word 'tool' appearing in it:
# 'Use the planner tool' is an instruction, and the model's reply
# 'None of the provided functions seem to be used…' is the failure, not a
# legitimate answer about capabilities (live evidence: plan_complex).
# The planner produces user-facing text; relay it when the request asked for a plan.
WANTS_PLAN = re.compile(r"\bplan(?:ning|ned)?\b|\broadmap\b|\bstep[- ]by[- ]step\b", re.I)

# 'compute … with a Python snippet' asks for a RESULT, not a sketch. When the answer
# carries a fenced block that never ran, the block is executed and its real output
# reported (dsa_lis / dsa_gcd_lcm / dsa_graph, live: tools=0, prose describing code).
WANTS_PY = re.compile(
    r"\b(?:using|with|in|write|run|compute|show)\b[^.\n]{0,24}\bpython\b"
    r"|\bpython\b[^.\n]{0,24}\b(?:snippet|code|program|script)\b", re.I)
# Volunteering code for a question that asked for a VALUE is the same unverified
# claim, whatever the user happened to type: math_sieve, live, answered 'how many
# primes between 1 and 100' with a fenced `def count_primes_up_to…` block and no
# number, because the request never said the word 'python'.
WANTS_RESULT = re.compile(
    r"\b(?:how many|how much|what is|what are|compute|calculate|evaluate|count|"
    r"find the value|which|list|print|output|result)\b", re.I)
PY_FENCE = re.compile(r"```(?:python|py)?[ \t]*\r?\n(.*?)```", re.S | re.I)

# A45a: does this snippet produce output of its own? If not, running it verbatim
# yields empty stdout and there is nothing to verify against — the exact dead end
# `dsa_gcd_lcm` hit in the live eval (the displayed code computed gcd/lcm into
# variables and never printed them, so "I ran it; it prints:" came back blank).
PRINTS_SRC = re.compile(
    r"\b(?:print|pprint)\s*\(|sys\.stdout|\.write\s*\(|\binput\s*\(", re.I)

# Appended ONLY when the snippet has no output statement, so a printing snippet
# still runs verbatim and nothing is ever executed twice. Bounded, and it prints
# the code's own computed values rather than guessing at them.
VALUE_READOUT = """

# --- appended by BEE: this snippet printed nothing, so report the values it computed
import types as _bee_types
_bee_rows = []
for _bee_k, _bee_v in list(globals().items()):
    if _bee_k.startswith("_") or isinstance(
            _bee_v, (_bee_types.ModuleType, _bee_types.FunctionType,
                    _bee_types.BuiltinFunctionType, type)):
        continue
    if isinstance(_bee_v, (int, float, str, bool, list, tuple, dict, set, frozenset)):
        _bee_rows.append((_bee_k, _bee_v))
for _bee_k, _bee_v in sorted(_bee_rows)[:12]:
    try:
        print(f"{_bee_k} = {repr(_bee_v)[:160]}")
    except Exception:
        pass
"""

ABOUT_TOOLS_TASK = re.compile(
    r"\b(?:which|what|all)\s+(?:[a-z]+\s+){0,3}(?:tools?|functions?|capabilit\w+|"
    r"permissions?|integrat\w+)\b"
    r"|\b(?:tools?|functions?|capabilit\w+)\s+(?:do\s+you\s+(?:have|support)|"
    r"are\s+(?:available|listed|provided))"
    r"|\b(?:do\s+you|can\s+you)\s+(?:have|use|list|show(?:\s+me)?)\s+(?:any|the|your)\s+"
    r"(?:tools?|functions?|capabilit\w+)", re.I)
META_RAMBLE_RE = re.compile(
    r"\b(?:no|without(?:\s+any)?)\s+(?:function|tool)\s*calls?\b"
    r"|\bno\s+(?:[a-z]+\s+){0,2}?(?:function|tool)\s*calls?\b"
    r"|\b(?:available|listed|provided)\s+(?:function|tool)s?\b"
    r"|\b(?:function|tool)s?\s+(?:were|was|are|is|were\s+not)\s+(?:not\s+)?(?:provided|available|given)\b"
    r"|\b(?:function|tool)s?\s+(?:provided|available|listed)\b"
    r"|\b(?:call|invoke)\s+(?:a|any|the)\s+(?:function|tool)\b"
    r"|\bmy\s+call\s+to\s+use\s+the\s+available\b"
    # dsa_lis, live: "…prior context to work with for the functions provided
    # earlier. Since no specific function call is mentioned, I can't provide
    # details on what action was intended." — none of the shapes above matched.
    r"|\b(?:didn'?t|did\s+not|haven'?t|have\s+not)\s+(?:receive|get|got)\b[^.\n]{0,48}"
    r"\b(?:function|tool|context)s?\b"
    r"|\bwhat\s+action\s+was\s+intended\b"
    # dsa_gcd_lcm, live (the last task still failing): '…the last message did not
    # contain any information to proceed with a function call. If you intended for me
    # to perform a specific action using one of these functions…'. Deliberately
    # tied to the asking-the-user-for-plumbing-input frame, so a legitimate answer
    # like 'the tool call failed with a timeout' is NOT treated as a ramble.
    r"|\b(?:proceed|continue|go\s+ahead)\b[^.\n]{0,32}\b(?:a|one|any|the)\s+(?:function|tool)s?\b"
    r"|\b(?:if\s+you\s+intended|please\s+provide\s+more\s+details|need\s+more\s+details)"
    r"[^.\n]{0,60}\b(?:function|tool)s?\b", re.I)


ABOUT_REFUSAL = re.compile(
    r'"blocked"|too many actions|not allowed|denied|"error"|error":', re.I)
# Loop-control payloads: the repeat/cache breaker's own note, which is plumbing and
# not evidence of anything (live: the honest fallback quoted it as 'the last thing a
# tool actually returned').
LOOP_CONTROL = re.compile(
    r'"note":\s*"(?:You already ran|.{0,60}has been called)', re.I)


# ------------------------------------------------------------------ detectors
def wants_plan(text: str) -> bool:
    """The request (or reply) is about planning."""
    return bool(WANTS_PLAN.search(text or ""))


def wants_python(text: str) -> bool:
    """The request explicitly asks for a Python snippet."""
    return bool(WANTS_PY.search(text or ""))


def wants_result(text: str) -> bool:
    """The request asks for a value/count/list — a result, not a sketch."""
    return bool(WANTS_RESULT.search(text or ""))


def asks_about_tools(text: str) -> bool:
    """The user is genuinely asking about the tool/capability surface."""
    return bool(ABOUT_TOOLS_TASK.search(text or ""))


def is_meta_ramble(text: str) -> bool:
    """The text talks about harness plumbing (functions/tools/budgets)."""
    return bool(META_RAMBLE_RE.search(text or ""))


def narrates_tool_call(text: str) -> bool:
    """The model describes an intended call instead of making it."""
    return bool(TOOL_INTENT_RE.search(text or ""))


def first_py_fence(text: str):
    """First fenced code block (match object with group(1)), or None."""
    return PY_FENCE.search(text or "")


def prints_output(src: str) -> bool:
    """The snippet prints/inputs on its own (no read-out needed)."""
    return bool(PRINTS_SRC.search(src or ""))


def is_harness_plumbing(text: str) -> bool:
    """Refusal/error/loop-control payload — the harness talking, not a fact."""
    return bool(ABOUT_REFUSAL.search(text or "") or LOOP_CONTROL.search(text or ""))
