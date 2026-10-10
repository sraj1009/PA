"""Real-client streaming contract (docs/TECHNICAL_DEBT.md A37).

Every previous streaming test used a *fake client that defined its own
`chat_stream`*, so the real `LLMClient` streaming path had never been executed
in 700+ tests. It contained two defects (an omitted `tools` argument and an
invalid `httpx.Timeout`) plus a partial-recovery branch that read an attribute
nothing ever sets. These tests drive the REAL class and fake only the transport.
"""
from __future__ import annotations

import json

from bee.agent.client import LLMClient
from bee.config import Config


class _FakeStream:
    def __init__(self, lines, fail_after=None):
        self._lines, self._fail_after = lines, fail_after

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for i, line in enumerate(self._lines):
            if self._fail_after is not None and i >= self._fail_after:
                raise RuntimeError("connection reset by peer")
            yield line


def _fake_http(monkeypatch, lines, fail_after=None, captured=None):
    from bee.agent import client as C

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, method, url, json=None, timeout=None):   # noqa: A002 - mirrors httpx
            if captured is not None:
                captured.update(method=method, url=url, payload=json, timeout=timeout)
            return _FakeStream(lines, fail_after)

    monkeypatch.setattr(C.httpx, "Client", _Client)


def _local_client():
    cfg = Config()
    cfg.ollama.base_url = "http://127.0.0.1:1"      # never dialled: httpx is faked
    return LLMClient(cfg)


def _nd(*parts):
    lines = [json.dumps({"message": {"content": p}, "done": False}) for p in parts]
    lines.append(json.dumps({"message": {}, "done": True,
                             "prompt_eval_count": 11, "eval_count": 7}))
    return lines


def test_native_ollama_stream_receives_tools_and_streams_tokens(monkeypatch):
    """A37a: the call site omitted `tools`; the TypeError was re-raised as a
    generic LLMError, so local streaming was dead whenever litellm is absent."""
    from bee.agent import client as C
    monkeypatch.setattr(C, "HAS_LITELLM", False)
    cap = {}
    _fake_http(monkeypatch, _nd("Hel", "lo"), captured=cap)
    got = []
    out = _local_client().chat_stream(
        "local", [{"role": "user", "content": "hi"}], on_token=got.append,
        tools=[{"type": "function", "function": {"name": "shell"}}])
    assert cap["payload"]["tools"][0]["function"]["name"] == "shell", "tools never reached the payload"
    assert cap["payload"]["stream"] is True
    assert got == ["Hel", "lo"] and out["content"] == "Hello"
    assert out["usage"] == {"prompt": 11, "completion": 7}


def test_native_ollama_stream_builds_a_valid_httpx_timeout(monkeypatch):
    """A37c: `Timeout(connect=, read=)` without a default raises ValueError in
    httpx; the constructor ran before the first request, so the path could not
    work even after the arity fix."""
    from bee.agent import client as C
    import httpx
    monkeypatch.setattr(C, "HAS_LITELLM", False)
    cap = {}
    _fake_http(monkeypatch, _nd("ok"), captured=cap)
    _local_client().chat_stream("local", [{"role": "user", "content": "hi"}],
                               on_token=lambda t: None, max_retries=0)
    assert isinstance(cap["timeout"], httpx.Timeout)
    assert cap["timeout"].connect == 6.0


def test_native_ollama_stream_accumulates_tool_calls(monkeypatch):
    from bee.agent import client as C
    monkeypatch.setattr(C, "HAS_LITELLM", False)
    lines = [json.dumps({"message": {"tool_calls": [
        {"function": {"name": "calculator", "arguments": {"a": 1}}}]}, "done": False})]
    _fake_http(monkeypatch, lines)
    out = _local_client().chat_stream("local", [{"role": "user", "content": "x"}],
                                      on_token=lambda t: None)
    assert out["tool_calls"][0]["name"] == "calculator"
    assert out["tool_calls"][0]["arguments"] == {"a": 1}


def test_tokens_already_reached_the_user_are_returned_when_the_stream_breaks(monkeypatch):
    """A37b: the recovery branch read `e._partial`, which nothing in the codebase
    ever set, so a mid-stream failure returned None and the loop lost an answer
    the user had already partly heard."""
    from bee.agent import client as C
    monkeypatch.setattr(C, "HAS_LITELLM", False)
    _fake_http(monkeypatch, _nd("The answer is 4", "2 and it works"), fail_after=1)
    got = []
    out = _local_client().chat_stream("local", [{"role": "user", "content": "hi"}],
                                      on_token=got.append, max_retries=0)
    assert got == ["The answer is 4"]
    assert out["content"] == "The answer is 4", out
    assert "error" in out


def test_litellm_path_gets_tools_and_returns_partial_text(monkeypatch):
    """Same two rules checked on the other provider branch."""
    from bee.agent import client as C
    seen = {}

    class _Boom:
        def __iter__(self):
            yield type("Ch", (), {"choices": [type("D", (), {
                "delta": type("X", (), {"content": "half", "tool_calls": None})()})()],
                "usage": None})()
            raise RuntimeError("boom")

    def fake_completion(**kw):
        seen.update(kw)
        return _Boom()

    monkeypatch.setattr(C, "HAS_LITELLM", True)
    monkeypatch.setattr(C.litellm, "completion", fake_completion)
    got = []
    out = _local_client().chat_stream("local", [{"role": "user", "content": "hi"}],
                                      on_token=got.append,
                                      tools=[{"type": "function"}], max_retries=0)
    assert seen["tools"] == [{"type": "function"}]
    assert out["content"] == "half" and got == ["half"]


# ------------------------------------------------------------------ embeddings

def test_embedding_uses_a_provider_ref_litellm_actually_maps(monkeypatch):
    """A38: `ollama_chat/` is a CHAT provider, so litellm raised
    LiteLLMUnknownProvider on EVERY embedding call and the blanket except dropped
    it into the native loop — a permanently dead primary path, invisible (A27a's
    species). The primary path must be the one that answers."""
    from bee.agent import client as C
    seen, native = {}, []

    def fake_embedding(**kw):
        seen.update(kw)
        return {"data": [{"embedding": [0.5, 0.25]} for _ in kw["input"]]}

    monkeypatch.setattr(C, "HAS_LITELLM", True)
    monkeypatch.setattr(C.litellm, "embedding", fake_embedding)
    monkeypatch.setattr(C.httpx, "post", lambda *a, **k: native.append(a))
    monkeypatch.setattr(C.LLMClient, "_has_ollama", lambda self: True)
    cfg = Config()
    cfg.ollama.embed_model = "nomic-embed-text"
    out = C.LLMClient(cfg).embed(["a", "b"])
    assert seen["model"] == "ollama/nomic-embed-text", seen
    assert seen["api_base"] == cfg.ollama.base_url
    assert out == [[0.5, 0.25], [0.5, 0.25]]
    assert native == [], "fell through to the per-text native loop"


def test_embedding_still_works_when_litellm_is_unavailable(monkeypatch, caplog):
    """The native loop is the safety net, so it stays reachable — and taking it is
    logged rather than silent (A7's rule about quiet failures)."""
    from bee.agent import client as C

    posts = []

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"embedding": [1.0]}

    monkeypatch.setattr(C, "HAS_LITELLM", True)
    monkeypatch.setattr(C.litellm, "embedding",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("unmapped provider")))
    monkeypatch.setattr(C.httpx, "post",
                        lambda url, json=None, timeout=None: posts.append((url, json)) or _R())
    monkeypatch.setattr(C.LLMClient, "_has_ollama", lambda self: True)
    caplog.set_level("DEBUG", logger="bee.llm")
    out = C.LLMClient(Config()).embed(["one text"])
    assert out == [[1.0]]
    assert posts and posts[0][1]["prompt"] == "one text"
    assert any("native Ollama" in r.getMessage() for r in caplog.records), caplog.text
