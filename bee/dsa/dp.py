"""Classic dynamic-programming recipes with complexity notes."""
from __future__ import annotations


def coin_change(coins, amount):
    """Min #coins to make amount, or -1. O(amount * len(coins))."""
    INF = float("inf")
    dp = [0] + [INF] * amount
    for a in range(1, amount + 1):
        for c in coins:
            if c <= a and dp[a - c] + 1 < dp[a]:
                dp[a] = dp[a - c] + 1
    return -1 if dp[amount] == INF else dp[amount]


def coin_change_count(coins, amount):
    """# of (unordered) ways to make amount. O(amount * len(coins))."""
    dp = [0] * (amount + 1)
    dp[0] = 1
    for c in coins:
        for a in range(c, amount + 1):
            dp[a] += dp[a - c]
    return dp[amount]


def knapsack(weights, values, capacity):
    """0/1 knapsack. Returns (max_value, chosen_indices). O(n * capacity)."""
    n = len(weights)
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        w, v = weights[i - 1], values[i - 1]
        for c in range(capacity + 1):
            dp[i][c] = dp[i - 1][c]
            if w <= c:
                dp[i][c] = max(dp[i][c], dp[i - 1][c - w] + v)
    # backtrack
    chosen, c = [], capacity
    for i in range(n, 0, -1):
        if dp[i][c] != dp[i - 1][c]:
            chosen.append(i - 1)
            c -= weights[i - 1]
    return dp[n][capacity], sorted(chosen)


def lcs(a, b):
    """Longest common subsequence length + one witness. O(n*m)."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    # backtrack one witness
    out, i, j = [], n, m
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            out.append(a[i - 1]); i -= 1; j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return dp[n][m], list(reversed(out))


def lis(arr):
    """Longest strictly-increasing subsequence length + one witness. O(n log n) (patience)."""
    import bisect
    tails = []
    tails_idx = []
    parent = [-1] * len(arr)
    for i, x in enumerate(arr):
        pos = bisect.bisect_left(tails, x)
        if pos == len(tails):
            tails.append(x)
            tails_idx.append(i)
        else:
            tails[pos] = x
            tails_idx[pos] = i
        if pos > 0:
            parent[i] = tails_idx[pos - 1]
    length = len(tails)
    out = []
    k = tails_idx[-1] if tails_idx else -1
    while k != -1:
        out.append(arr[k])
        k = parent[k]
    return length, list(reversed(out))


def edit_distance(a, b):
    """Levenshtein distance (insert/delete/substitute). O(n*m)."""
    n, m = len(a), len(b)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, m + 1):
            cur = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = cur
    return dp[m]


def rod_cut(prices, n):
    """Max revenue cutting a rod of length n (prices[i] for length i+1). O(n^2)."""
    dp = [0] * (n + 1)
    cut = [0] * (n + 1)
    for i in range(1, n + 1):
        best = -1
        for j in range(1, i + 1):
            v = prices[j - 1] + dp[i - j]
            if v > best:
                best, cut[i] = v, j
        dp[i] = best
    return dp[n], cut
