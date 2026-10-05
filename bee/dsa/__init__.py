"""BEE DSA library — curated, tested building blocks + benchmark harness.

Usage:
    from bee.dsa import sorting, graphs, dp, UnionFind, Trie, SegmentTree, SparseTable
    from bee.dsa.bench import run_bench, check
"""
from .sorting import (insertion_sort, bubble_sort, merge_sort, quick_sort,
                      heap_sort, counting_sort, timsort_reference, ALL as SORTS)
from .union_find import UnionFind
from .trie import Trie
from . import graphs, dp
from .segment_tree import SegmentTree
from .sparse_table import SparseTable
from . import binary_tree, heap

__all__ = [
    "insertion_sort", "bubble_sort", "merge_sort", "quick_sort",
    "heap_sort", "counting_sort", "timsort_reference", "SORTS",
    "UnionFind", "Trie", "graphs", "dp", "SegmentTree", "SparseTable",
    "binary_tree", "heap",
]
