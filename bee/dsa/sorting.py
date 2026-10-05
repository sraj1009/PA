"""Sorting implementations — reference library for the DSA benchmark harness.

Every function: (seq, key=None, reverse=False) -> list. O-complexities in docstrings.
"""
from __future__ import annotations

import heapq
import random


def insertion_sort(arr, key=None, reverse=False):
    """O(n^2) time, O(1) extra. Best for tiny / nearly-sorted inputs."""
    a = list(arr)
    for i in range(1, len(a)):
        v, k = a[i], key(a[i]) if key else a[i]
        j = i - 1
        while j >= 0:
            kj = key(a[j]) if key else a[j]
            shift = (kj < k) if reverse else (kj > k)
            if shift:
                a[j + 1] = a[j]
                j -= 1
            else:
                break
        a[j + 1] = v
    return a


def bubble_sort(arr, key=None, reverse=False):
    """O(n^2) with early-exit on a quiet pass. Educational only."""
    a = list(arr)
    n = len(a)
    for i in range(n):
        swapped = False
        for j in range(n - 1 - i):
            kj = key(a[j]) if key else a[j]
            kn = key(a[j + 1]) if key else a[j + 1]
            if (kj < kn) if reverse else (kj > kn):
                a[j], a[j + 1] = a[j + 1], a[j]
                swapped = True
        if not swapped:
            break
    return a


def merge_sort(arr, key=None, reverse=False):
    """O(n log n) stable, O(n) extra."""
    a = list(arr)
    if len(a) <= 1:
        return a
    mid = len(a) // 2
    left = merge_sort(a[:mid], key, reverse)
    right = merge_sort(a[mid:], key, reverse)
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        kl = key(left[i]) if key else left[i]
        kr = key(right[j]) if key else right[j]
        # On equal keys, always take LEFT first => stable in both directions.
        pick_left = (kl >= kr) if reverse else (kl <= kr)
        if pick_left:
            out.append(left[i]); i += 1
        else:
            out.append(right[j]); j += 1
    out.extend(left[i:])
    out.extend(right[j:])
    return out


def quick_sort(arr, key=None, reverse=False):
    """O(n log n) avg (median-of-three pivot), O(log n) stack. Worst O(n^2) on bad pivots."""
    a = list(arr)
    def ks(x):
        return key(x) if key else x
    def q(lo, hi):
        if lo >= hi:
            return
        if hi - lo < 16:
            insertion(a, lo, hi, ks, reverse)
            return
        m = (lo + hi) // 2
        p = _median3_idx(a, lo, m, hi, ks)
        a[p], a[hi] = a[hi], a[p]
        i, j = lo, hi - 1
        pivot = a[hi]
        kp = ks(pivot)
        while True:
            while (ks(a[i]) > kp) if reverse else (ks(a[i]) < kp):
                i += 1
            while (ks(a[j]) < kp) if reverse else (ks(a[j]) > kp):
                j -= 1
            if i >= j:
                break
            a[i], a[j] = a[j], a[i]
            i += 1; j -= 1
        a[i], a[hi] = a[hi], a[i]
        q(lo, i - 1)
        q(i + 1, hi)
    def insertion(a, lo, hi, ks, reverse):
        for i in range(lo + 1, hi + 1):
            v = a[i]
            j = i - 1
            while j >= lo and ((ks(a[j]) < ks(v)) if reverse else (ks(a[j]) > ks(v))):
                a[j + 1] = a[j]
                j -= 1
            a[j + 1] = v
    q(0, len(a) - 1)
    return a


def _median3_idx(a, i, j, k, ks):
    """Return the index (of i/j/k) holding the median value."""
    x, y, z = ks(a[i]), ks(a[j]), ks(a[k])
    if (x <= y <= z) or (z <= y <= x):
        return j
    if (y <= x <= z) or (z <= x <= y):
        return i
    return k


def heap_sort(arr, key=None, reverse=False):
    """O(n log n), O(1) extra beyond input copy. Min-heap; sign-flip for reverse."""
    import heapq
    sign = -1 if reverse else 1
    h = []
    for i, x in enumerate(arr):
        kx = key(x) if key else x
        heapq.heappush(h, (sign * kx, i, x))
    out = []
    while h:
        out.append(heapq.heappop(h)[2])
    return out


def counting_sort(arr, min_v=0, max_v=None):
    """O(n + k) for small integer domains only."""
    a = [int(x) for x in arr]
    if not a:
        return a
    lo = min_v if min_v is not None else min(a)
    hi = max_v if max_v is not None else max(a)
    if hi - lo > 100000:
        raise ValueError("counting_sort: domain too large, use another sort")
    bucket = [0] * (hi - lo + 1)
    for x in a:
        bucket[x - lo] += 1
    out = []
    for i, c in enumerate(bucket):
        out.extend([i + lo] * c)
    return out


def timsort_reference(arr, key=None, reverse=False):
    """CPython's built-in (reference for correctness checks)."""
    return sorted(arr, key=key, reverse=reverse)


ALL = {
    "insertion": insertion_sort,
    "bubble": bubble_sort,
    "merge": merge_sort,
    "quick": quick_sort,
    "heap": heap_sort,
    "timsort": timsort_reference,
}
