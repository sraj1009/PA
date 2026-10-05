"""DSA library correctness — runs the full verify_all() harness.

~6,000+ assertions across sorting / union-find / segment tree / sparse table /
trie / DP / graphs / binary tree / heap, each algorithm cross-checked against an
independent reference (built-ins, O(n^2), O(2^n) brute force, heapq). Any
regression fails here.
"""
from bee.dsa import verify


def test_dsa_all_modules_verified():
    res = verify.verify_all()
    failed = {k: v for k, v in res.items() if not v["ok"]}
    assert not failed, f"DSA verify failures: {failed}"
    total = sum(v.get("checks", 0) for v in res.values())
    assert total > 3000, f"expected thousands of DSA checks, got {total}"


def test_merge_sort_stable_reverse():
    """Regression: merge_sort must be stable under reverse=True (equal keys keep order)."""
    from bee.dsa import sorting
    words = ["bb", "a", "ccc", "dd", "ee", "f"]
    assert sorting.merge_sort(words, key=len, reverse=True) == sorted(words, key=len, reverse=True)


def test_dsa_modules_importable():
    from bee.dsa import (sorting, union_find, segment_tree, sparse_table, trie,
                         dp, graphs, binary_tree, heap)  # noqa
    assert len(sorting.ALL) >= 6
    assert callable(binary_tree.lca) and callable(heap.quickselect)
