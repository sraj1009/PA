"""Trie (prefix tree) — autocomplete, spellcheck, prefix queries.

O(L) per op where L = string length.
"""
from __future__ import annotations


class _Node:
    __slots__ = ("children", "is_word", "count")

    def __init__(self):
        self.children: dict[str, "_Node"] = {}
        self.is_word = False
        self.count = 0


class Trie:
    def __init__(self):
        self.root = _Node()
        self.size = 0

    def insert(self, word: str):
        node = self.root
        for ch in word:
            node = node.children.setdefault(ch, _Node())
            node.count += 1
        if not node.is_word:
            node.is_word = True
            self.size += 1

    def __contains__(self, word: str) -> bool:
        node = self.root
        for ch in word:
            node = node.children.get(ch)
            if node is None:
                return False
        return node is not None and node.is_word

    def starts_with(self, prefix: str) -> bool:
        node = self.root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return False
        return True

    def words_with_prefix(self, prefix: str, limit: int = 100) -> list[str]:
        node = self.root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return []
        out: list[str] = []

        def dfs(n: _Node, acc: str):
            if len(out) >= limit:
                return
            if n.is_word:
                out.append(acc)
            for ch in sorted(n.children):
                dfs(n.children[ch], acc + ch)

        dfs(node, prefix)
        return out

    def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        return self.words_with_prefix(prefix, limit=limit)
