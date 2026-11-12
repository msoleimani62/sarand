"""Cycles between repository modules (R14-A, plan section 2).

Strongly connected components of the internal import graph (iterative Tarjan: no
recursion, so a deep graph cannot hit the recursion limit), plus modules that import
themselves. Only edges that resolved to a repository module with confidence
definite or probable count; an `unknown` edge is never a dependency.

A cycle is `eager` when it survives after removing type-only and lazy (in-function)
imports, that is when it can fail at import time; a cycle that exists only through
those is reported but not eager.

چرخه‌های import میان ماژول‌ها؛ یال با اعتماد unknown هرگز وابستگی حساب نمی‌شود.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sarand.structure.model import (
    CONF_UNKNOWN,
    FLAG_LAZY,
    FLAG_TYPE_ONLY,
    TARGET_INTERNAL,
    Cycle,
    Edge,
)


def _graph(edges: Iterable[Edge], *, eager_only: bool) -> dict[str, list[str]]:
    graph: dict[str, set[str]] = {}
    for edge in edges:
        if edge.target_class != TARGET_INTERNAL or edge.confidence == CONF_UNKNOWN:
            continue
        if not edge.target:
            continue
        if eager_only and (FLAG_LAZY in edge.flags or FLAG_TYPE_ONLY in edge.flags):
            continue
        graph.setdefault(edge.source, set()).add(edge.target)
        graph.setdefault(edge.target, set())
    return {node: sorted(targets) for node, targets in sorted(graph.items())}


def _components(graph: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan's algorithm without recursion. Returns every component."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    found: list[list[str]] = []
    counter = 0
    for start in graph:
        if start in index:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            node, position = work.pop()
            if position == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            neighbours = graph[node]
            descended = False
            for i in range(position, len(neighbours)):
                nxt = neighbours[i]
                if nxt not in index:
                    work.append((node, i + 1))
                    work.append((nxt, 0))
                    descended = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if descended:
                continue
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    component.append(top)
                    if top == node:
                        break
                found.append(sorted(component))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return found


def _cyclic(component: list[str], graph: dict[str, list[str]]) -> bool:
    return len(component) > 1 or component[0] in graph.get(component[0], [])


def find_cycles(edges: Sequence[Edge]) -> tuple[Cycle, ...]:
    """Every cycle of the internal import graph, sorted, with its edges."""
    graph = _graph(edges, eager_only=False)
    eager_graph = _graph(edges, eager_only=True)
    eager_sets = [set(c) for c in _components(eager_graph) if _cyclic(c, eager_graph)]
    cycles: list[Cycle] = []
    for component in _components(graph):
        if not _cyclic(component, graph):
            continue
        members = set(component)
        inside = tuple(
            e
            for e in edges
            if e.source in members
            and e.target in members
            and e.target_class == TARGET_INTERNAL
            and e.confidence != CONF_UNKNOWN
        )
        eager = any(group <= members for group in eager_sets)
        cycles.append(Cycle(tuple(component), eager, inside))
    cycles.sort(key=lambda c: c.modules)
    return tuple(cycles)
