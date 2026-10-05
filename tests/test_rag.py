"""RAG — trigger detection + deterministic recall@k. Run: python tests/test_rag.py"""
import sys
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
