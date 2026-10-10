"""A55: the verify-retry prompt must not become the model's subject.

On a failing verification the loop re-asks for the answer. The old ask opened with
an ALL-CAPS status code and a dump of internal check names, and the 3B model made
that phrase the topic instead of finishing the task — live eval `guard_blocked`,
2026-10-10: `tools=0`, output
"To properly address the issue of SELF-VERIFICATION_FAILED, we need to ensure that
each function call is correctly formatted with all required arguments included
within a JSON object enclosed by …".
"""
from __future__ import annotations

from tests.test_kernel_integration import _no_fastpath, make_kernel

PHANTOM = ("Here is the result:\n- File created: `eval_probe.txt`\n"
           "- Content: BEE EVAL OK")
HONEST = ("I did not create eval_probe.txt — nothing I ran was able to write it, "
          "so there is no file to read back.")
TASK = ("Create a file called eval_probe.txt containing exactly: BEE EVAL OK, "
        "then read it back and confirm its content.")

# plumbing the model must never be handed as a topic
_JARGON = ("SELF-VERIFICATION", "verify", "verdict", "check:", "finding", "JSON")


def _second_call_request(client):
    return [m for m in client.calls[1][1] if m["role"] == "user"][-1]["content"]


def test_the_retry_names_no_mechanism(tmp_path, monkeypatch):
    _no_fastpath(monkeypatch)
    _k, client, _ctx = make_kernel(tmp_path, [PHANTOM, HONEST])
    client.calls.clear()
    _k.run(TASK)
    assert len(client.calls) >= 2, "no retry round happened"
    retry = _second_call_request(client)
    for leak in _JARGON:
        assert leak not in retry, f"{leak!r} reached the model: {retry[:300]}"


def test_the_retry_restates_the_request(tmp_path, monkeypatch):
    _no_fastpath(monkeypatch)
    _k, client, _ctx = make_kernel(tmp_path, [PHANTOM, HONEST])
    client.calls.clear()
    _k.run(TASK)
    retry = _second_call_request(client)
    assert "eval_probe.txt" in retry and "BEE EVAL OK" in retry


def test_the_retry_still_says_what_was_wrong(tmp_path, monkeypatch):
    """The rewording must not lose the finding — plain words, same information."""
    _no_fastpath(monkeypatch)
    _k, client, _ctx = make_kernel(tmp_path, [PHANTOM, HONEST])
    client.calls.clear()
    _k.run(TASK)
    retry = _second_call_request(client)
    assert "does not exist" in retry, retry[:400]


def test_the_corrected_answer_is_the_one_delivered(tmp_path, monkeypatch):
    _no_fastpath(monkeypatch)
    # the kernel retries a FAILED task once, so the whole script is consumed twice
    k, _client, _ctx = make_kernel(tmp_path, [PHANTOM] + [HONEST] * 8)
    res = k.run(TASK)
    assert res.output.startswith(HONEST[:40]), res.output
    assert res.verify in ("pass", "warn"), res.verify
