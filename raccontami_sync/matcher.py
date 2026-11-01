"""Match a speech transcript (word list) against the book's word list.

Strategy, meant to be ported to Kotlin later:
1. Anchors: n-grams that occur exactly once in both sequences.
2. Keep the longest chain of anchors that is increasing in both sequences.
3. Recurse into the regions between anchors with smaller n; once a region is
   small, fill it with a Needleman-Wunsch alignment that accepts fuzzy matches.
4. Drop isolated matches (they show up inside skipped regions by chance).
"""

from __future__ import annotations

import bisect
from collections import defaultdict

from rapidfuzz.distance import Levenshtein

DP_MAX_CELLS = 250_000


def similar(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    return Levenshtein.normalized_similarity(a, b) >= 0.75


def _lis(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Longest chain strictly increasing in both coordinates (pairs sorted by first)."""
    tails: list[int] = []
    tails_k: list[int] = []
    prev = [-1] * len(pairs)
    for k, (_, j) in enumerate(pairs):
        pos = bisect.bisect_left(tails, j)
        if pos == len(tails):
            tails.append(j)
            tails_k.append(k)
        else:
            tails[pos] = j
            tails_k[pos] = k
        prev[k] = tails_k[pos - 1] if pos > 0 else -1
    out = []
    k = tails_k[-1] if tails_k else -1
    while k != -1:
        out.append(pairs[k])
        k = prev[k]
    return out[::-1]


def _anchors(A, B, a0, a1, b0, b1, n):
    ca: dict = defaultdict(list)
    cb: dict = defaultdict(list)
    for i in range(a0, a1 - n + 1):
        ca[tuple(A[i:i + n])].append(i)
    for j in range(b0, b1 - n + 1):
        cb[tuple(B[j:j + n])].append(j)
    pairs = sorted((ia[0], cb[g][0]) for g, ia in ca.items() if len(ia) == 1 and len(cb.get(g, ())) == 1)
    chain = _lis(pairs)
    expanded: list[tuple[int, int]] = []
    for i, j in chain:
        for k in range(n):
            p = (i + k, j + k)
            if not expanded or (p[0] > expanded[-1][0] and p[1] > expanded[-1][1]):
                expanded.append(p)
    return expanded


def _dp(A, B, a0, a1, b0, b1):
    n, m = a1 - a0, b1 - b0
    INF = float("inf")
    # cost matrix, row-major lists
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        D[i][0] = float(i)
    for j in range(1, m + 1):
        D[0][j] = float(j)
    for i in range(1, n + 1):
        ai = A[a0 + i - 1]
        Di, Dp = D[i], D[i - 1]
        for j in range(1, m + 1):
            bj = B[b0 + j - 1]
            sub = 0.0 if ai == bj else (0.3 if similar(ai, bj) else 1.0)
            best = Dp[j - 1] + sub
            if Dp[j] + 1.0 < best:
                best = Dp[j] + 1.0
            if Di[j - 1] + 1.0 < best:
                best = Di[j - 1] + 1.0
            Di[j] = best
    out = []
    i, j = n, m
    while i > 0 and j > 0:
        ai, bj = A[a0 + i - 1], B[b0 + j - 1]
        sub = 0.0 if ai == bj else (0.3 if similar(ai, bj) else 1.0)
        if D[i][j] == D[i - 1][j - 1] + sub:
            if sub < 1.0:
                out.append((a0 + i - 1, b0 + j - 1))
            i, j = i - 1, j - 1
        elif D[i][j] == D[i - 1][j] + 1.0:
            i -= 1
        else:
            j -= 1
    return out[::-1]


def match(A: list[str], B: list[str]) -> list[tuple[int, int]]:
    """Return monotonic (index in A, index in B) pairs of matching words."""
    result: list[tuple[int, int]] = []

    def solve(a0, a1, b0, b1, n):
        if a0 >= a1 or b0 >= b1:
            return
        if (a1 - a0) * (b1 - b0) <= DP_MAX_CELLS:
            result.extend(_dp(A, B, a0, a1, b0, b1))
            return
        if n < 2:
            return  # large region with no anchors: treat as unmatched
        chain = _anchors(A, B, a0, a1, b0, b1, n)
        if not chain:
            solve(a0, a1, b0, b1, n - 1)
            return
        pi, pj = a0 - 1, b0 - 1
        for i, j in chain:
            solve(pi + 1, i, pj + 1, j, n)
            result.append((i, j))
            pi, pj = i, j
        solve(pi + 1, a1, pj + 1, b1, n)

    solve(0, len(A), 0, len(B), 5)
    result.sort()
    # enforce strict monotonicity (safety) and drop isolated matches
    mono: list[tuple[int, int]] = []
    for p in result:
        if not mono or (p[0] > mono[-1][0] and p[1] > mono[-1][1]):
            mono.append(p)
    a_idx = [p[0] for p in mono]
    kept = []
    for i, j in mono:
        lo = bisect.bisect_left(a_idx, i - 5)
        hi = bisect.bisect_right(a_idx, i + 5)
        if hi - lo >= 4:
            kept.append((i, j))
    return kept
