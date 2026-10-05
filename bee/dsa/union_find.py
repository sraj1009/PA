"""Union-Find / Disjoint Set Union with path compression + union by rank.

Near O(1) amortized (inverse Ackermann). Classic use: connectivity, cycle
detection in undirected graphs, Kruskal MST, offline DSU.
"""
from __future__ import annotations


class UnionFind:
    def __init__(self, n: int = 0, items=None):
        if items is not None:
            self.map = {x: i for i, x in enumerate(items)}
            self.n = len(items)
        else:
            self.map = {}
            self.n = n
        self.parent = list(range(self.n))
        self.rank = [0] * self.n
        self.components = self.n

    def find(self, x) -> int:
        x = self.map.get(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path halving
            self.parent[x], x = self.parent[root], self.parent[x]
        return root

    def union(self, a, b) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        self.components -= 1
        return True

    def connected(self, a, b) -> bool:
        return self.find(a) == self.find(b)

    def group(self) -> dict:
        out: dict = {}
        for i in range(self.n):
            out.setdefault(self.find(i), []).append(i)
        return out
