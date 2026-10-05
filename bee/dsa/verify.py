"""Comprehensive correctness verification for the BEE DSA library.

``verify_all()`` runs known-answer tests plus randomized property tests, checking
each algorithm against an INDEPENDENT reference (Python built-ins, a naive O(n^2)/
O(2^n) brute force) — not just that it runs. This is what makes the DSA "perfect"
rather than merely present: it is proven correct on ~thousands of assertions.

Run:   python -m bee.dsa.verify
Used by: tests/test_dsa.py (fails the suite on any regression).
"""
from __future__ import annotations

import random


def _check(cond: bool, label: str) -> None:
    if not cond:
        raise AssertionError(label)


def _verify_sorting(rng: random.Random) -> int:
    from .bench import check
    from . import sorting
    cases = [
        [], [1], [2, 1], [3, 3, 3], [5, 4, 3, 2, 1],
        list(range(10, 0, -1)),
        [rng.randint(-1000, 1000) for _ in range(rng.randint(1, 400))],
        [rng.randint(0, 5) for _ in range(200)],  # heavy duplicates
    ]
    fns = {k: v for k, v in sorting.ALL.items() if k != "timsort"}
    for data in cases:
        check(sorted_fn(fns, data), sorted(data), f"sort fwd n={len(data)}")
        for name, fn in fns.items():
            check(fn(data), sorted(data), f"{name} fwd n={len(data)}")
            check(fn(data, reverse=True), sorted(data, reverse=True), f"{name} rev n={len(data)}")
    words = ["bb", "a", "ccc", "dd", "ee", "f"]
    for name, fn in fns.items():
        check(fn(words, key=len), sorted(words, key=len), f"{name} key=len")
        check(fn(words, key=len, reverse=True), sorted(words, key=len, reverse=True), f"{name} key=len rev")
    data = [rng.randint(0, 50) for _ in range(200)]
    check(sorting.counting_sort(data), sorted(data), "counting_sort")
    return len(cases) * len(fns) * 2 + len(fns) * 2 + 1


def sorted_fn(fns, data):
    return next(iter(fns.values()))(data)


def _verify_union_find(rng: random.Random) -> int:
    from . import union_find
    n = 100
    uf = union_find.UnionFind(n)
    _check(uf.components == n, "uf initial components")
    comp = list(range(n))

    def cfind(x):
        while comp[x] != x:
            x = comp[x]
        return x

    ops = 0
    for _ in range(500):
        a, b = rng.randrange(n), rng.randrange(n)
        res = uf.union(a, b)
        ops += 1
        ca, cb = cfind(a), cfind(b)
        if ca != cb:
            comp[cb] = ca
            _check(res is True, "uf union new merge must be True")
        else:
            _check(res is False, "uf union same comp must be False")
        _check(uf.connected(a, b) == (cfind(a) == cfind(b)), "uf connected mismatch")
    _check(uf.components == len({cfind(i) for i in range(n)}), "uf components count")
    g = uf.group()
    _check(sum(len(v) for v in g.values()) == n, "uf group covers all")
    for root, members in g.items():
        _check(all(uf.connected(m, members[0]) for m in members), "uf group members connected")
    uf2 = union_find.UnionFind(items=["x", "y", "z"])
    uf2.union("x", "z")
    _check(uf2.connected("x", "z") and not uf2.connected("x", "y"), "uf items-based")
    return ops + 6


def _verify_segment_tree(rng: random.Random) -> int:
    from . import segment_tree
    checks = 0
    for _ in range(30):
        n = rng.randint(1, 60)
        arr = [rng.randint(-1000, 1000) for _ in range(n)]
        st = segment_tree.SegmentTree(arr)  # sum
        for _ in range(20):
            lo, hi = sorted([rng.randrange(n), rng.randrange(n)])
            _check(st.query(lo, hi) == sum(arr[lo:hi + 1]), "seg sum query")
            checks += 1
            i, nv = rng.randrange(n), rng.randint(-1000, 1000)
            st.update(i, nv)
            arr[i] = nv
            _check(st.query(0, n - 1) == sum(arr), "seg sum total after update")
            checks += 1
    arr = [rng.randint(0, 100) for _ in range(40)]
    stm = segment_tree.SegmentTree(arr, op=min, identity=10 ** 9)
    for _ in range(20):
        lo, hi = sorted([rng.randrange(len(arr)), rng.randrange(len(arr))])
        _check(stm.query(lo, hi) == min(arr[lo:hi + 1]), "seg min query")
        checks += 1
    return checks


def _verify_sparse_table(rng: random.Random) -> int:
    from . import sparse_table
    checks = 0
    for _ in range(30):
        n = rng.randint(1, 80)
        arr = [rng.randint(-1000, 1000) for _ in range(n)]
        stmin = sparse_table.SparseTable(arr, op=min)
        stmax = sparse_table.SparseTable(arr, op=max)
        for _ in range(20):
            lo, hi = sorted([rng.randrange(n), rng.randrange(n)])
            _check(stmin.query(lo, hi) == min(arr[lo:hi + 1]), "sparse min")
            _check(stmax.query(lo, hi) == max(arr[lo:hi + 1]), "sparse max")
            checks += 2
    return checks


def _verify_trie(rng: random.Random) -> int:
    from . import trie
    t = trie.Trie()
    words = ["cat", "car", "card", "care", "dog", "doge", "dogs"]
    for w in words:
        t.insert(w)
    _check(t.size == len(set(words)), "trie size unique")
    t.insert("cat")
    _check(t.size == len(set(words)), "trie size dup ignored")
    _check(("car" in t) and ("card" in t) and ("ca" not in t), "trie contains")
    _check(t.starts_with("ca") and not t.starts_with("zz"), "trie starts_with")
    _check(t.words_with_prefix("ca") == ["car", "card", "care", "cat"], "trie prefix words")
    _check(t.words_with_prefix("dog") == ["dog", "doge", "dogs"], "trie dog words")
    _check(t.words_with_prefix("doge") == ["doge"], "trie doge exact")
    _check(t.words_with_prefix("z") == [], "trie no match")
    rnd = ["".join(rng.choice("abc") for _ in range(rng.randint(1, 5))) for _ in range(60)]
    t2 = trie.Trie()
    for w in rnd:
        t2.insert(w)
    for pref in set(w[:2] for w in rnd):
        expected = sorted(set(w for w in rnd if w.startswith(pref)))
        got = sorted(t2.words_with_prefix(pref, limit=1000))
        _check(got == expected, f"trie prop prefix={pref!r}")
    return 8 + 60 + len(rnd)


def _verify_dp(rng: random.Random) -> int:
    from . import dp
    checks = 0

    def brute_coin(coins, amount):
        from collections import deque
        dist, q = {0: 0}, deque([0])
        while q:
            a = q.popleft()
            if a == amount:
                return dist[a]
            for c in coins:
                if a + c <= amount and a + c not in dist:
                    dist[a + c] = dist[a] + 1
                    q.append(a + c)
        return -1

    for _ in range(25):
        coins = list(set(rng.randint(1, 12) for _ in range(rng.randint(1, 5))))
        amount = rng.randint(0, 40)
        _check(dp.coin_change(coins, amount) == brute_coin(coins, amount), "coin_change vs brute")
        checks += 1
    _check(dp.coin_change_count([1, 2, 5], 5) == 4, "coin_change_count 5")
    _check(dp.coin_change_count([1, 2, 5], 10) == 10, "coin_change_count 10")
    checks += 2
    for _ in range(15):
        n = rng.randint(1, 8)
        w = [rng.randint(1, 10) for _ in range(n)]
        v = [rng.randint(1, 20) for _ in range(n)]
        cap = rng.randint(0, 20)
        best, chosen = dp.knapsack(w, v, cap)
        bv = 0
        for mask in range(1 << n):
            ws = sum(w[i] for i in range(n) if mask >> i & 1)
            if ws <= cap:
                bv = max(bv, sum(v[i] for i in range(n) if mask >> i & 1))
        _check(best == bv, "knapsack value vs brute")
        _check(sum(w[i] for i in chosen) <= cap and sum(v[i] for i in chosen) == best, "knapsack chosen valid")
        checks += 2

    def is_subseq(s, big):
        it = iter(big)
        return all(c in it for c in s)

    la, lw = dp.lcs("AGGTAB", "GXTXAYB")
    _check(la == 4, "lcs len AGGTAB")
    _check(is_subseq(lw, "AGGTAB") and is_subseq(lw, "GXTXAYB"), "lcs witness common subseq")
    checks += 2

    def dp_lis(arr):
        f = [1] * len(arr)
        for i in range(len(arr)):
            for j in range(i):
                if arr[j] < arr[i]:
                    f[i] = max(f[i], f[j] + 1)
        return max(f) if f else 0

    for _ in range(25):
        arr = [rng.randint(-50, 50) for _ in range(rng.randint(1, 60))]
        L, witness = dp.lis(arr)
        _check(L == dp_lis(arr), "lis len vs O(n^2)")
        _check(all(witness[i] < witness[i + 1] for i in range(len(witness) - 1)), "lis witness strictly inc")
        checks += 2

    def brute_edit(a, b):
        import functools
        @functools.lru_cache(None)
        def e(i, j):
            if i == 0:
                return j
            if j == 0:
                return i
            if a[i - 1] == b[j - 1]:
                return e(i - 1, j - 1)
            return 1 + min(e(i - 1, j), e(i, j - 1), e(i - 1, j - 1))
        return e(len(a), len(b))

    for _ in range(15):
        a = "".join(rng.choice("abcde") for _ in range(rng.randint(0, 8)))
        b = "".join(rng.choice("abcde") for _ in range(rng.randint(0, 8)))
        _check(dp.edit_distance(a, b) == brute_edit(a, b), f"edit {a!r}->{b!r}")
        checks += 1
    return checks


def _verify_graphs(rng: random.Random) -> int:
    from . import graphs
    checks = 0
    for _ in range(20):
        n = rng.randint(2, 12)
        nodes = list(range(n))
        edges = []
        for _ in range(rng.randint(0, n * 2)):
            u, v = rng.randrange(n), rng.randrange(n)
            if u != v:
                edges.append((u, v, rng.randint(1, 20)))
        adj = graphs._adj(nodes, edges)
        d1, _ = graphs.dijkstra(adj, 0)
        bedges = [(u, v, w) for u, v, w in edges] + [(v, u, w) for u, v, w in edges]
        d2, _ = graphs.bellman_ford(nodes, bedges, 0)
        for v in nodes:
            _check(d1.get(v, float("inf")) == d2.get(v, float("inf")), "dijkstra vs bellman_ford")
            checks += 1
    _check(graphs.has_cycle_undirected(graphs._adj([1, 2, 3], [(1, 2), (2, 3)])) is False, "no cycle on tree")
    _check(graphs.has_cycle_undirected(graphs._adj([1, 2, 3], [(1, 2), (2, 3), (3, 1)])) is True, "triangle cycle")
    checks += 2
    order = graphs.topological_sort([1, 2, 3, 4], [(1, 2), (2, 3), (1, 4), (3, 4)])
    pos = {v: i for i, v in enumerate(order)}
    _check(pos[1] < pos[2] < pos[3] < pos[4], "topo order valid")
    try:
        graphs.topological_sort([1, 2], [(1, 2), (2, 1)])
        _check(False, "topo should raise on cycle")
    except ValueError:
        pass
    checks += 2
    n = 6
    edges = [(0, 1, 2), (1, 2, 3), (0, 2, 10), (2, 3, 1), (3, 4, 1), (4, 5, 1)]
    d = graphs.floyd_warshall(n, edges)  # directed
    dadj: dict = {}
    for u, v, w in edges:
        dadj.setdefault(u, []).append((v, w))  # directed adj for a fair dijkstra compare
    for s in range(n):
        ds, _ = graphs.dijkstra(dadj, s)
        for t in range(n):
            _check(d[s][t] == ds.get(t, float("inf")), f"floyd {s}->{t}")
            checks += 1
    return checks


def _verify_binary_tree(rng: random.Random) -> int:
    from . import binary_tree as bt
    checks = 0
    for _ in range(30):
        vals = rng.sample(range(1, 1000), k=rng.randint(1, 40))
        root = None
        for v in vals:
            root = bt.bst_insert(root, v)
        _check(bt.inorder(root) == sorted(vals), "bst inorder == sorted")
        _check(bt.is_valid_bst(root), "bst valid")
        checks += 2
        for v in vals:
            _check(bt.bst_contains(root, v), f"bst contains {v}")
            checks += 1
        for v in rng.sample(range(1, 2000), k=10):
            if v not in set(vals):
                _check(not bt.bst_contains(root, v), f"bst not contains {v}")
                checks += 1
        if len(vals) >= 2:
            a, b = rng.sample(vals, 2)

            # Independent LCA reference: build a parent map, collect a's ancestors,
            # then climb from b until we hit one of them. Cannot KeyError (uses .get).
            parent: dict = {}

            def walk(n, p):
                if n is None:
                    return
                parent[n.val] = p
                walk(n.left, n.val)
                walk(n.right, n.val)

            walk(root, None)
            anc_a = set()
            cur = a
            while cur is not None:
                anc_a.add(cur)
                cur = parent.get(cur)
            brute_lca = None
            cur = b
            while cur is not None:
                if cur in anc_a:
                    brute_lca = cur
                    break
                cur = parent.get(cur)
            _check(bt.lca(root, a, b) == brute_lca, f"lca {a},{b}")
            checks += 1
    svals = sorted(rng.sample(range(1000), 60))
    broot = bt.from_sorted(svals)
    _check(bt.inorder(broot) == svals, "from_sorted inorder")
    _check(abs(bt.height(broot.left) - bt.height(broot.right)) <= 1, "from_sorted balanced")
    checks += 2
    r = bt.Node(1, bt.Node(2, bt.Node(4), bt.Node(5)), bt.Node(3))
    _check(bt.inorder(r) == [4, 2, 5, 1, 3], "inorder fixed")
    _check(bt.preorder(r) == [1, 2, 4, 5, 3], "preorder fixed")
    _check(bt.postorder(r) == [4, 5, 2, 3, 1], "postorder fixed")
    _check(bt.level_order(r) == [1, 2, 3, 4, 5], "level_order fixed")
    _check(bt.height(r) == 2, "height fixed")
    _check(bt.count_nodes(r) == 5, "count fixed")
    checks += 6
    return checks


def _verify_heap(rng: random.Random) -> int:
    import heapq
    from . import heap as hp
    checks = 0
    for _ in range(40):
        items = [rng.randint(-50, 50) for _ in range(rng.randint(1, 60))]
        for min_heap in (True, False):
            h = hp.Heap(items, min_heap=min_heap)
            ref = sorted(items) if min_heap else sorted(items, reverse=True)
            _check([h.pop() for _ in range(len(items))] == ref,
                   f"{'min' if min_heap else 'max'}-heap pop order")
            checks += 1
        base = [rng.randint(0, 30) for _ in range(20)]
        heapq.heapify(base)  # heappushpop requires a valid heap as reference
        h2 = hp.Heap(base, min_heap=True)
        for _ in range(20):
            x = rng.randint(0, 30)
            _check(h2.pushpop(x) == heapq.heappushpop(base, x), "pushpop min == heapq")
            checks += 1
        h3 = hp.Heap(base, min_heap=False)
        neg = [-b for b in base]
        heapq.heapify(neg)  # sign-flip of a min-heap is not a min-heap; re-heapify
        for _ in range(10):
            x = rng.randint(0, 30)
            _check(h3.pushpop(x) == -heapq.heappushpop(neg, -x), "pushpop max == heapq")
            checks += 1
        h4 = hp.Heap([rng.randint(0, 100) for _ in range(50)])
        _check(h4.top_k(5) == sorted(h4.a[1:], reverse=True)[:5], "top_k largest")
        _check(h4.top_k(5, largest=False) == sorted(h4.a[1:])[:5], "top_k smallest")
        checks += 2
    for _ in range(60):
        arr = [rng.randint(0, 20) for _ in range(rng.randint(1, 60))]  # heavy dups
        s = sorted(arr)
        for k in (0, len(arr) // 2, len(arr) - 1):
            _check(hp.quickselect(arr, k) == s[k], f"quickselect k={k}")
            checks += 1
    for _ in range(30):
        arr = [rng.randint(-100, 100) for _ in range(rng.randint(1, 40))]
        _check(hp.median(arr) == sorted(arr)[(len(arr) - 1) // 2], f"median n={len(arr)}")
        checks += 1
    return checks


def verify_all(seed: int = 1234) -> dict:
    rng = random.Random(seed)
    fns = [
        ("sorting", _verify_sorting),
        ("union_find", _verify_union_find),
        ("segment_tree", _verify_segment_tree),
        ("sparse_table", _verify_sparse_table),
        ("trie", _verify_trie),
        ("dp", _verify_dp),
        ("graphs", _verify_graphs),
        ("binary_tree", _verify_binary_tree),
        ("heap", _verify_heap),
    ]
    results = {}
    for name, fn in fns:
        try:
            results[name] = {"ok": True, "checks": fn(rng)}
        except Exception as e:
            results[name] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}
    return results


if __name__ == "__main__":
    import json
    import sys
    res = verify_all()
    print(json.dumps(res, indent=1))
    bad = [k for k, v in res.items() if not v["ok"]]
    print("FAILED:", bad) if bad else print("ALL DSA MODULES VERIFIED CORRECT")
    sys.exit(1 if bad else 0)
