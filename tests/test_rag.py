"""RAG — trigger detection + deterministic recall@k. Run: python tests/test_rag.py"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bee.brain import rag  # noqa: E402

CHUNKS = [
    ("profile.md", "User has an NVIDIA RTX 3050 8GB GPU on Windows."),
    ("longterm.md", "BEE was created on 2026-10-04 as a local agent."),
    ("diary/1.md", "Completed the Docker sandbox build with Playwright."),
    ("diary/2.md", "User prefers dark cinematic UI with lime accents."),
    ("diary/3.md", "Fixed the quicksort median-of-three pivot bug."),
    ("skills/dsa/SKILL.md", "Dijkstra handles non-negative weights; use Bellman-Ford otherwise."),
    ("longterm.md", "Cloud escalation uses openrouter deepseek chat."),
    ("diary/4.md", "The nomic embed model has 768 dimensions."),
]
QUESTIONS = [
    ("what GPU do I have?", "3050"),
    ("when was bee created?", "2026-10-04"),
    ("what did we do with docker?", "sandbox"),
    ("what ui style do I like?", "dark cinematic"),
    ("what was the sorting bug?", "quicksort"),
    ("which shortest path for negative edges?", "Bellman-Ford"),
    ("which cloud model escalates?", "openrouter"),
    ("embed dimension?", "768"),
]


def test_triggers():
    assert rag.needs_context("do you remember what my GPU is?")
    assert rag.needs_context("continue where we left off last time")
    assert rag.needs_context("what did I tell you about my machine?")
    assert not rag.needs_context("compute 2+2")
    assert not rag.needs_context("list the files")


def test_recall():
    out = rag.recall_eval(CHUNKS, QUESTIONS, k=3)
    assert out["n"] == 8
    assert out["recall_at_k"] >= 0.875, out  # 7/8 at minimum; expect 8/8
    print("   recall@3:", out["recall_at_k"])


def test_recall_k5_better():
    out5 = rag.recall_eval(CHUNKS, QUESTIONS, k=5)
    out3 = rag.recall_eval(CHUNKS, QUESTIONS, k=3)
    assert out5["recall_at_k"] >= out3["recall_at_k"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
    print(f"\n{len(fns) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


# ---------------- incremental indexing: a new fact is findable NOW (A28)
class _FakeStore:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls: list[tuple[str, int]] = []

    def replace_source(self, src, chunks):
        if self.fail:
            raise RuntimeError("embedder unreachable")
        self.calls.append((src, len(list(chunks))))
        return 1


def test_mark_dirty_queues_and_flush_trims_it(tmp_path, monkeypatch):
    from bee.memory import search as S
    dirty = tmp_path / "dirty.jsonl"
    monkeypatch.setattr(S, "_dirty_file", lambda: dirty)
    S.mark_dirty(tmp_path / "profile.md")
    S.mark_dirty(tmp_path / "profile.md")          # deduped, not doubled
    S.mark_dirty(tmp_path / "diary.md")
    assert len(S.pending_paths()) == 2, S.pending_paths()

    store = _FakeStore()
    monkeypatch.setattr(S, "get_store", lambda ctx: store)
    monkeypatch.setattr(S.md, "chunk_md", lambda p: [(str(p), "a chunk of memory")])
    res = S.flush_dirty(None)
    assert res["ok"] and res["files"] == 2, res
    assert S.pending_paths() == [], "queue must be empty after a successful flush"


def test_failed_flush_keeps_the_queue_for_retry(tmp_path, monkeypatch):
    """The whole point of a durable queue: an unreachable embedder must not
    silently drop the fact until the next 12 h rebuild."""
    from bee.memory import search as S
    dirty = tmp_path / "dirty.jsonl"
    monkeypatch.setattr(S, "_dirty_file", lambda: dirty)
    monkeypatch.setattr(S, "get_store", lambda ctx: _FakeStore(fail=True))
    monkeypatch.setattr(S.md, "chunk_md", lambda p: [(str(p), "x")])
    S.mark_dirty(tmp_path / "profile.md")
    res = S.flush_dirty(None)
    assert not res["ok"] and res["failed"] == 1, res
    assert len(S.pending_paths()) == 1, "the un-indexed file must still be queued"

    ok = _FakeStore()
    monkeypatch.setattr(S, "get_store", lambda ctx: ok)
    res2 = S.flush_dirty(None)
    assert res2["ok"] and len(ok.calls) == 1, res2
    assert S.pending_paths() == []


def test_unavailable_store_does_not_clear_the_queue(tmp_path, monkeypatch):
    from bee.memory import search as S
    dirty = tmp_path / "dirty.jsonl"
    monkeypatch.setattr(S, "_dirty_file", lambda: dirty)
    monkeypatch.setattr(S, "get_store", lambda ctx: False)   # lancedb absent
    S.mark_dirty(tmp_path / "profile.md")
    res = S.flush_dirty(None)
    assert not res["ok"] and res["files"] == 1, res
    assert len(S.pending_paths()) == 1


def test_diary_write_marks_the_file_dirty(tmp_path, monkeypatch):
    """The write path only queues — it must never block on an embedding call."""
    from bee import paths
    from bee.memory import md, search as S
    seen = []
    monkeypatch.setattr(S, "mark_dirty", lambda p: seen.append(str(p)))
    monkeypatch.setattr(paths, "DIARY_DIR", tmp_path)
    p = md.diary_add("the user prefers Neovim")
    assert seen == [str(p)], seen


def test_flush_job_is_registered_and_stoppable_by_the_switch():
    """A maintenance job the `scheduler.enabled` switch does not stop is the
    defect class this repo already recorded — the new job must be in both lists."""
    from bee import scheduler
    from bee.automation.worker import FUNCTIONS
    assert "bee.scheduler.flush_memory_index" in FUNCTIONS
    assert "memory_index_flush" in scheduler._SYSTEM_JOB_IDS
    src = scheduler._register_nightly_jobs.__code__.co_consts
    assert any("memory_index_flush" == c for c in src if isinstance(c, str))


def test_flush_drives_the_real_store_class(tmp_path, monkeypatch):
    """Regression against the way this feature was first written wrong:
    `replace_source` ended up indented inside `get_store`, so it never existed on
    the class — production raised AttributeError while every fake-store test above
    stayed green. Only the embedder is faked here; the store, the table and the
    queue are the real ones."""
    from bee import paths
    from bee.memory import md, search as S

    class _FakeClient:
        def embed(self, texts):
            return [[0.1] * 768 for _ in texts]

    assert hasattr(S._VecStore, "replace_source"), "must be a method on the class"
    vec_dir = tmp_path / "vectors"
    vec_dir.mkdir()
    monkeypatch.setattr(paths, "VECTOR_DIR", vec_dir)
    S._cache = None
    try:
        f = tmp_path / "profile.md"
        f.write_text("## hardware\nNVIDIA RTX 3050 8 GB graphics card\n", encoding="utf-8")
        ctx = types.SimpleNamespace(cfg=None, client=_FakeClient())
        S.mark_dirty(f)
        res = S.flush_dirty(ctx)
        assert res["ok"] and res["files"] == 1 and res["chunks"] >= 1, res
        assert S.pending_paths() == []
        rows = S.get_store(ctx)._table().count_rows()
        assert rows >= 1, rows
        srcs = {r["source"] for r in S.get_store(ctx)._table().search(
            [0.1] * 768).limit(5).to_list()}
        assert str(f) in srcs, srcs
    finally:
        S._cache = None


def test_stale_index_self_heals_without_a_write(tmp_path, monkeypatch):
    """A queue is only as good as its last write: an index left stale (empty
    queue, files never embedded) would otherwise wait for the 12 h rebuild — or
    for a write that never comes."""
    from bee import paths
    from bee.memory import md, search as S

    class _FakeClient:
        def embed(self, texts):
            return [[0.2] * 768 for _ in texts]

    vec = tmp_path / "vectors"; vec.mkdir()
    monkeypatch.setattr(paths, "VECTOR_DIR", vec)
    S._cache = None
    try:
        a = tmp_path / "profile.md"
        a.write_text("## hardware\nRTX 3050 8 GB\n", encoding="utf-8")
        b = tmp_path / "longterm.md"
        b.write_text("## facts\nthe project is called BEE\n", encoding="utf-8")
        monkeypatch.setattr(md, "all_chunks",
                            lambda: [(str(a), "RTX 3050 8 GB"), (str(b), "project BEE")])
        ctx = types.SimpleNamespace(cfg=None, client=_FakeClient())
        assert S.pending_paths() == []
        res = S.flush_dirty(ctx)          # nothing queued -> staleness scan
        assert res["ok"] and res["files"] == 2, res
        assert S.pending_paths() == []
        # second flush is a no-op: everything is already indexed
        res2 = S.flush_dirty(ctx)
        assert res2["files"] == 0, res2
    finally:
        S._cache = None


def test_diary_logs_are_not_indexed_as_memory(tmp_path):
    """The diary's `## HH:MM:SS [model=…] task:/result:` blocks are a LOG of past
    exchanges. They quote the question, so they embed closest to the next time the
    user asks the same thing — ~1,300 a day crowding the real facts out, which is
    why 'Remember the hardware of this machine?' answered 'nothing stored'.
    Genuine notes (no [model=] tag) must stay."""
    from bee.memory import md

    f = tmp_path / "2026-10-08.md"
    f.write_text(
        "# diary\n\n"
        "## 09:12:03\nnote (fast path): the wifi password was rotated to hunter2\n\n"
        "## 21:41:16 [model=local]\ntask: Search your memory for 'hardware'\n"
        "result: I'm sorry, but I don't have specific information about the GPU.\n\n"
        "## 21:52:04 [model=local|cloud]\ntask: what time is it\nresult: It's 21:52.\n",
        encoding="utf-8")
    chunks = [c for _s, c in md.chunk_md(f)]
    assert len(chunks) == 1, chunks
    assert "wifi password" in chunks[0]
    assert not any("I'm sorry" in c for c in chunks)
    assert not any("what time is it" in c for c in chunks)
