"""Segment tree with range query + point update. O(log n) each.

Default op = sum. Pass any associative op (min, max, gcd...) with an identity.
"""
from __future__ import annotations

import operator


class SegmentTree:
    def __init__(self, arr, op=operator.add, identity=0):
        n = len(arr)
        self.n = n
        self.op = op
        self.identity = identity
        size = 1
        while size < n:
            size <<= 1
        self.size = size
        self.tree = [identity] * (2 * size)
        for i, v in enumerate(arr):
            self.tree[size + i] = v
        for i in range(size - 1, 0, -1):
            self.tree[i] = op(self.tree[2 * i], self.tree[2 * i + 1])

    def update(self, i: int, value):
        k = self.size + i
        self.tree[k] = value
        while k > 1:
            k >>= 1
            self.tree[k] = self.op(self.tree[2 * k], self.tree[2 * k + 1])

    def query(self, lo: int, hi: int):
        """Inclusive range [lo, hi]."""
        if lo > hi:
            return self.identity
        l, r = self.size + lo, self.size + hi
        res_l, res_r = self.identity, self.identity
        while l <= r:
            if l % 2 == 1:
                res_l = self.op(res_l, self.tree[l]); l += 1
            if r % 2 == 0:
                res_r = self.op(self.tree[r], res_r); r -= 1
            l >>= 1
            r >>= 1
        return self.op(res_l, res_r)
