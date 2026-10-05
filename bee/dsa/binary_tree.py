"""Binary tree + BST: traversals, insert/search, validation, LCA, balanced build.

Every operation is O(h) or O(n) and verified in verify.py against independent
references (sorted() for BST inorder, brute-force parent paths for LCA).
"""
from __future__ import annotations

from collections import deque
from typing import List, Optional


class Node:
    __slots__ = ("val", "left", "right")

    def __init__(self, val, left: Optional["Node"] = None, right: Optional["Node"] = None):
        self.val, self.left, self.right = val, left, right


# ---- traversals -------------------------------------------------------------

def inorder(root: Optional[Node]) -> list:
    out: list = []

    def rec(n):
        if n is None:
            return
        rec(n.left)
        out.append(n.val)
        rec(n.right)

    rec(root)
    return out


def preorder(root: Optional[Node]) -> list:
    out: list = []

    def rec(n):
        if n is None:
            return
        out.append(n.val)
        rec(n.left)
        rec(n.right)

    rec(root)
    return out


def postorder(root: Optional[Node]) -> list:
    out: list = []

    def rec(n):
        if n is None:
            return
        rec(n.left)
        rec(n.right)
        out.append(n.val)

    rec(root)
    return out


def level_order(root: Optional[Node]) -> list:
    """BFS; matches [node per level] flattened left-to-right."""
    if root is None:
        return []
    out: list = []
    q = deque([root])
    while q:
        n = q.popleft()
        out.append(n.val)
        if n.left:
            q.append(n.left)
        if n.right:
            q.append(n.right)
    return out


def height(root: Optional[Node]) -> int:
    """-1 for empty, 0 for a single node."""
    if root is None:
        return -1
    return 1 + max(height(root.left), height(root.right))


def count_nodes(root: Optional[Node]) -> int:
    if root is None:
        return 0
    return 1 + count_nodes(root.left) + count_nodes(root.right)


# ---- BST operations ---------------------------------------------------------

def bst_insert(root: Optional[Node], val) -> Node:
    if root is None:
        return Node(val)
    n = root
    while True:
        if val < n.val:
            if n.left is None:
                n.left = Node(val)
                break
            n = n.left
        else:
            if n.right is None:
                n.right = Node(val)
                break
            n = n.right
    return root


def bst_contains(root: Optional[Node], val) -> bool:
    n = root
    while n is not None:
        if val == n.val:
            return True
        n = n.left if val < n.val else n.right
    return False


def is_valid_bst(root: Optional[Node]) -> bool:
    """Strict BST: left < node < right, enforced over the whole subtree."""
    def rec(n: Optional[Node], lo: Optional[float], hi: Optional[float]) -> bool:
        if n is None:
            return True
        if lo is not None and n.val <= lo:
            return False
        if hi is not None and n.val >= hi:
            return False
        return rec(n.left, lo, n.val) and rec(n.right, n.val, hi)

    return rec(root, None, None)


def lca(root: Optional[Node], a, b):
    """Lowest common ancestor of values a and b in a BST (or None if not a BST path)."""
    n = root
    while n is not None:
        if a < n.val and b < n.val:
            n = n.left
        elif a > n.val and b > n.val:
            n = n.right
        else:
            return n.val
    return None


def from_sorted(vals: List) -> Optional[Node]:
    """Balanced BST from sorted values (median becomes the root)."""
    def rec(lo: int, hi: int) -> Optional[Node]:
        if lo > hi:
            return None
        mid = (lo + hi) // 2
        return Node(vals[mid], rec(lo, mid - 1), rec(mid + 1, hi))

    return rec(0, len(vals) - 1)
