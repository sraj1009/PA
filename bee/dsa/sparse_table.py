"""Sparse table for static range min/max queries. Build O(n log n), query O(1).

Idempotent ops only (min, max, gcd, bitwise & / |). For sum use SegmentTree.
"""
from __future__ import annotations

import math


class SparseTable:
    def __init__(self, arr, op=min):
        self.n = len(arr)
        self.op = op
        if self.n == 0:
            self.log = []
            self.table = []
            return
        K = self.n.bit_length()
        self.log = [0] * (self.n + 1)
        for i in range(2, self.n + 1):
            self.log[i] = self.log[i // 2] + 1
        self.table = [list(arr)]
        for k in range(1, K):
            prev = self.table[-1]
            span = 1 << (k - 1)
            row = [op(prev[i], prev[i + span]) for i in range(self.n - (1 << k) + 1)]
            self.table.append(row)
        self.K = K

    def query(self, lo: int, hi: int):
        """Inclusive [lo, hi]. O(1)."""
        if self.n == 0:
            raise ValueError("empty table")
        if lo > hi:
            raise ValueError("lo > hi")
        k = self.log[hi - lo + 1]
        row = self.table[k]
        return self.op(row[lo], row[hi - (1 << k) + 1])
