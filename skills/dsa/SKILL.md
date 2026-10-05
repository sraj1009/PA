# dsa

description: Solve/optimize data-structure & algorithm problems — understand, pick approach, state Big-O, implement, test, benchmark.

## When to use
Any task mentioning algorithms, data structures, complexity, "optimize", sorting, graphs, DP, or interview-style coding problems.

## How
1. Understand the problem; name inputs/outputs and the core operation (search/range/path/order).
2. Pick the approach by domain:
   - ordering → bee.dsa.sorting (merge O(n log n) stable; quick avg O(n log n); insertion for tiny/nearly-sorted)
   - connectivity/components → UnionFind (near-O(1) amortized)
   - prefix/autocomplete → Trie (O(L))
   - shortest path → graphs.dijkstra (non-neg, O((V+E) log V)); neg edges → bellman_ford; all-pairs → floyd_warshall
   - cycle/topo order → topological_sort (Kahn), has_cycle_undirected
   - range sum + updates → SegmentTree (O(log n)); static range min/max → SparseTable (O(1) query)
   - DP recipes → bee.dsa.dp (coin_change, knapsack, lcs, lis O(n log n), edit_distance, rod_cut)
3. State Big-O (time + space) before coding.
4. Implement or import from bee.dsa; never rewrite a library function.
5. VERIFY with the benchmark harness:
   ```python
   from bee.dsa.bench import check, run_bench
   check(my_fn(data), reference_fn(data), label="correctness")
   print(run_bench(my_fn, "my_fn", data))
   ```
6. Benchmark report: `python -m bee.dsa.bench [n]` → evals/dsa_bench.json
7. If you write a NEW algorithm: add it to bee/dsa/, add a test in tests/test_dsa.py, run `python -m pytest tests/ -q`.

## Gotchas
- dijkstra raises on negative weights (use bellman_ford).
- SparseTable is for idempotent ops (min/max/gcd) only — sums need SegmentTree.
- counting_sort rejects domains > 100k.
- Always check reverse=True and key= paths — they break most naive sorts.
- Tests: python -m pytest tests/test_dsa.py -q must pass before claiming done.
