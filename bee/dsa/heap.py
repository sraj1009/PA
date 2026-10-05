"""Binary heap (min/max) + quickselect — independent of `heapq` internals.

Verified in verify.py against the `heapq` built-in and `sorted()`, so the
hand-rolled sift logic is proven correct, not just present.
"""
from __future__ import annotations

from typing import Callable, List, Optional


class Heap:
    """1-indexed binary heap. min_heap=True gives a min-heap (smallest on top)."""

    def __init__(self, iterable=(), *, min_heap: bool = True,
                 key: Optional[Callable] = None):
        self.min = min_heap
        self.key = key
        self.a: list = [None]  # index 0 unused
        for x in iterable:
            self.push(x)

    def _k(self, x):
        return self.key(x) if self.key is not None else x

    def _better(self, x, y) -> bool:
        """True if x has higher priority than y (should sit above it)."""
        kx, ky = self._k(x), self._k(y)
        return kx < ky if self.min else kx > ky

    def __len__(self) -> int:
        return len(self.a) - 1

    def __bool__(self) -> bool:
        return len(self.a) > 1

    def peek(self):
        return self.a[1] if len(self.a) > 1 else None

    def _sift_up(self, i: int) -> None:
        a = self.a
        while i > 1:
            p = i // 2
            if self._better(a[i], a[p]):
                a[i], a[p] = a[p], a[i]
                i = p
            else:
                break

    def _sift_down(self, i: int) -> None:
        a = self.a
        n = len(a)
        while True:
            l, r, m = 2 * i, 2 * i + 1, i
            if l < n and self._better(a[l], a[m]):
                m = l
            if r < n and self._better(a[r], a[m]):
                m = r
            if m == i:
                break
            a[i], a[m] = a[m], a[i]
            i = m

    def push(self, x):
        self.a.append(x)
        self._sift_up(len(self.a) - 1)
        return x

    def pop(self):
        if len(self.a) < 2:
            raise IndexError("pop from an empty heap")
        top, last = self.a[1], self.a.pop()
        if len(self.a) > 1:
            self.a[1] = last
            self._sift_down(1)
        return top

    def pushpop(self, x):
        """Push x then pop the top, atomically. O(log n). Returns min(x, old_top),
        matching heapq.heappushpop exactly."""
        if len(self.a) > 1:
            if self._better(x, self.a[1]):
                return x  # x is the new minimum: pushed then popped, heap unchanged
            top = self.a[1]
            self.a[1] = x
            self._sift_down(1)
            return top
        self.push(x)  # empty heap: push then pop == x
        return self.pop()

    def top_k(self, k: int, largest: bool = True) -> list:
        """The k largest (default) or k smallest items currently in the heap."""
        items = sorted(self.a[1:], key=self._k, reverse=largest)
        return items[:k]


def quickselect(arr: List, k: int, *, key: Optional[Callable] = None):
    """k-th smallest (0-indexed) element in expected O(n) via 3-way quickselect.

    Robust to duplicates (Dutch-national-flag partition). Verified against
    sorted(arr, key=key)[k] in verify.py.
    """
    a = list(arr)
    kf = key or (lambda x: x)
    lo, hi = 0, len(a) - 1
    while lo < hi:
        pv = kf(a[(lo + hi) // 2])
        lt, i, gt = lo, lo, hi
        while i <= gt:
            ki = kf(a[i])
            if ki < pv:
                a[lt], a[i] = a[i], a[lt]
                lt += 1
                i += 1
            elif ki > pv:
                a[gt], a[i] = a[i], a[gt]
                gt -= 1
            else:
                i += 1
        if k < lt:
            hi = lt - 1
        elif k > gt:
            lo = gt + 1
        else:
            return a[k]
    return a[lo]


def median(arr: List, *, key: Optional[Callable] = None):
    """Median (lower-middle for even n) in expected O(n) via quickselect."""
    a = list(arr)
    n = len(a)
    if n == 0:
        raise ValueError("median of empty sequence")
    if n == 1:
        return a[0]
    return quickselect(a, n // 2, key=key) if n % 2 == 1 else quickselect(a, n // 2 - 1, key=key)
