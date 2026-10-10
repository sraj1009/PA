"""Graph algorithms on adjacency-list dicts: {node: [(neighbor, weight), ...]}.

Undirected graphs: add both directions. Weights default to 1.
"""
from __future__ import annotations

import heapq
from collections import deque, defaultdict


def _adj(nodes=None, edges=None, weighted=False):
    g = defaultdict(list)
    for n in (nodes or []):
        g.setdefault(n, [])
    for e in (edges or []):
        if len(e) == 2:
            u, v = e
            g[u].append((v, 1))
            g[v].append((u, 1))
        else:
            u, v, w = e
            g[u].append((v, w))
            g[v].append((u, w))
    return dict(g)


def bfs(adj: dict, start):
    """BFS: returns (order, dist, parent). O(V+E)."""
    order, dist, parent = [], {}, {}
    dist[start] = 0
    q = deque([start])
    seen = {start}
    while q:
        u = q.popleft()
        order.append(u)
        for v, _w in adj.get(u, []):
            if v not in seen:
                seen.add(v)
                dist[v] = dist[u] + 1
                parent[v] = u
                q.append(v)
    return order, dist, parent


def dfs_order(adj: dict, start):
    """Iterative DFS order. O(V+E)."""
    seen, order = set(), []
    stack = [start]
    while stack:
        u = stack.pop()
        if u in seen:
            continue
        seen.add(u)
        order.append(u)
        for v, _w in reversed(adj.get(u, [])):
            if v not in seen:
                stack.append(v)
    return order


def dijkstra(adj: dict, start):
    """Dijkstra (non-negative weights): returns (dist, prev); dist[node] = shortest distance. O((V+E) log V)."""
    dist = {start: 0}
    prev = {}
    pq = [(0, start)]
    seen = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in seen:
            continue
        seen.add(u)
        for v, w in adj.get(u, []):
            if w < 0:
                raise ValueError("dijkstra: negative edge weight — use bellman_ford")
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def path(prev: dict, start, target):
    if target not in prev and target != start:
        return None
    out = [target]
    while out[-1] != start:
        out.append(prev[out[-1]])
    return list(reversed(out))


def bellman_ford(nodes, edges, start):
    """O(V*E). Handles negative edges; detects negative cycles. edges: [(u, v, w)]."""
    dist = {n: float("inf") for n in nodes}
    prev = {}
    dist[start] = 0
    for _ in range(len(nodes) - 1):
        for u, v, w in edges:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                prev[v] = u
    for u, v, w in edges:
        if dist[u] + w < dist[v]:
            raise ValueError("negative cycle detected")
    return dist, prev


def floyd_warshall(n: int, edges):
    """All-pairs shortest paths on 0..n-1. O(n^3). edges: [(u, v, w)]."""
    INF = float("inf")
    d = [[INF] * n for _ in range(n)]
    for i in range(n):
        d[i][i] = 0
    for u, v, w in edges:
        d[u][v] = min(d[u][v], w)
    for k in range(n):
        dk = d[k]
        for i in range(n):
            dik = d[i][k]
            if dik == INF:
                continue
            di = d[i]
            for j in range(n):
                if dik + dk[j] < di[j]:
                    di[j] = dik + dk[j]
    return d


def has_cycle_undirected(adj: dict) -> bool:
    seen = set()

    def dfs(u, p):
        seen.add(u)
        for v, _ in adj.get(u, []):
            if v not in seen:
                if dfs(v, u):
                    return True
            elif v != p:
                return True
        return False

    for n in adj:
        if n not in seen and dfs(n, None):
            return True
    return False


def topological_sort(nodes, edges):
    """Kahn's algorithm. Returns an order or raises on cycle. Edges (u, v): u before v."""
    indeg = {n: 0 for n in nodes}
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        indeg[v] += 1
    q = deque(n for n in nodes if indeg[n] == 0)
    order = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(order) != len(nodes):
        raise ValueError("cycle detected — no topological order")
    return order


def build_adj(nodes=None, edges=None) -> dict:
    """Undirected adjacency dict from edges [(u, v)] (weight 1) or [(u, v, w)]."""
    return _adj(nodes, edges)
