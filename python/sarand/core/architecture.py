"""Quick Context layer L3, part 1: the architecture block (docs/QUICK_CONTEXT_DESIGN.md,
section 6.1).

Built ONLY from fields that exist in `ReportData`: components, workspace
members, entry points, Compose services, Kubernetes and Helm items, with file
counts taken from `included_files` by path prefix. No import graph, no layers
inferred from names, no line counts (per-file lines are not in the report).

A pure function of `ReportData`: no clock, no environment, stable order, every
list capped with the dropped items counted as "(+N more)". Worst case is about
2 KiB of plain text; a test pins it.

لایه‌ی L3، بخش اول: بلوک معماری. فقط از فیلدهای موجود در `ReportData`:
اجزا، اعضای workspace، نقاط ورود، سرویس‌های Compose و آیتم‌های Kubernetes/Helm،
با تعداد فایل بر پایه‌ی پیشوند مسیر. بدون گراف import و بدون حدس از نام‌ها.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sarand.core.risks import DISPLAY_CAP, RULES, RiskReport, evaluate_risks
from sarand.models.results import ReportData

_CLIP = 80
_MAX_COMPONENTS = 10
_MAX_MEMBERS = 10
_MAX_ENTRY_POINTS = 8
_MAX_COMPOSE_FILES = 5
_MAX_SERVICES = 8
_MAX_HELM = 6
_MAX_OVERLAYS = 6


@dataclass
class Architecture:
    """The L3 architecture block. Plain data, JSON-serialisable via `asdict`.
    Every item is already a short plain-text line."""

    components: list[str] = field(default_factory=list)
    workspaces: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    compose: list[str] = field(default_factory=list)
    kubernetes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.components
            or self.workspaces
            or self.entry_points
            or self.compose
            or self.kubernetes
        )


def _clip(text: str, limit: int = _CLIP) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _capped(items: list[str], limit: int) -> list[str]:
    if len(items) <= limit:
        return items
    return [*items[:limit], f"(+{len(items) - limit} more)"]


def _file_counts(data: ReportData, paths: list[str]) -> dict[str, int]:
    """Files of `included_files` under each path ("." means all of them)."""
    posix = [p.as_posix() for p in data.included_files]
    counts: dict[str, int] = {}
    for path in paths:
        if path in (".", ""):
            counts[path] = len(posix)
        else:
            prefix = path.rstrip("/") + "/"
            counts[path] = sum(1 for p in posix if p.startswith(prefix))
    return counts


def _components(data: ReportData) -> list[str]:
    info = data.components
    if info is None:
        return []
    shown = info.components[:_MAX_COMPONENTS]
    counts = _file_counts(data, [c.path for c in shown])
    lines = [
        _clip(
            f"{c.path} ({c.role}{', ' + c.kind if c.kind else ''}"
            f"{'; ' + ', '.join(c.languages) if c.languages else ''})"
            f" -- {counts[c.path]} file(s)"
        )
        for c in shown
    ]
    hidden = max(info.total_components, len(info.components)) - len(shown)
    if hidden > 0:
        lines.append(f"(+{hidden} more)")
    return lines


def _workspaces(data: ReportData) -> list[str]:
    lines: list[str] = []
    for ws in data.all_workspaces:
        shown = ws.members[:_MAX_MEMBERS]
        counts = _file_counts(data, [m.path for m in shown])
        members = [_clip(f"{m.path} ({counts[m.path]} file(s))", 60) for m in shown]
        members = _capped(members, _MAX_MEMBERS)
        if len(ws.members) > _MAX_MEMBERS:
            members[-1] = f"(+{len(ws.members) - _MAX_MEMBERS} more)"
        lines.append(
            _clip(
                f"{ws.kind}: {len(ws.members)} member(s)"
                + (": " + ", ".join(members) if members else ""),
                400,
            )
        )
    return lines


def _compose(data: ReportData) -> list[str]:
    if data.compose is None:
        return []
    lines: list[str] = []
    for file in data.compose.files[:_MAX_COMPOSE_FILES]:
        services = [
            _clip(
                s.name
                + (" (build)" if s.builds else "")
                + (f" ({s.image})" if s.image and not s.builds else ""),
                50,
            )
            for s in file.services
        ]
        lines.append(
            _clip(
                f"{file.path}: {len(file.services)} service(s)"
                + (
                    ": " + ", ".join(_capped(services, _MAX_SERVICES))
                    if services
                    else ""
                ),
                300,
            )
        )
    hidden = len(data.compose.files) - _MAX_COMPOSE_FILES
    if hidden > 0:
        lines.append(f"(+{hidden} more compose file(s))")
    return lines


def _kubernetes(data: ReportData) -> list[str]:
    info = data.kubernetes
    if info is None:
        return []
    lines: list[str] = []
    if info.helm_charts:
        charts = [
            _clip(f"{c.name or c.path}{' ' + c.version if c.version else ''}", 40)
            for c in info.helm_charts
        ]
        lines.append(
            f"Helm: {len(charts)} chart(s): " + ", ".join(_capped(charts, _MAX_HELM))
        )
    if info.kustomize_overlays:
        overlays = [_clip(o.path, 40) for o in info.kustomize_overlays]
        lines.append(
            f"Kustomize: {len(overlays)} overlay(s): "
            + ", ".join(_capped(overlays, _MAX_OVERLAYS))
        )
    if info.total_manifest_files:
        lines.append(f"Raw manifests: {info.total_manifest_files} file(s)")
    return lines


def build_architecture(data: ReportData) -> Architecture:
    """Build the architecture block. Pure and deterministic."""
    return Architecture(
        components=_components(data),
        workspaces=_workspaces(data),
        entry_points=_capped(
            [_clip(e, 60) for e in data.detection.entry_points], _MAX_ENTRY_POINTS
        ),
        compose=_compose(data),
        kubernetes=_kubernetes(data),
    )


def risk_lines(report: RiskReport) -> list[str]:
    """Risk lines as plain text: one per risk, the limitation of every fired
    rule once, then the rules that could not be evaluated."""
    if not report.risks:
        lines = ["Risks (rule-based): none identified"]
    else:
        lines = ["Risks (rule-based):"]
        for risk in report.risks[:DISPLAY_CAP]:
            refs = f" [{'; '.join(risk.evidence_refs)}]" if risk.evidence_refs else ""
            lines.append(f"  - {risk.rule_id} ({risk.severity}): {risk.reason}{refs}")
        hidden = len(report.risks) - DISPLAY_CAP
        if hidden > 0:
            lines.append(f"  - (+{hidden} more)")
        lines.append("Limitations:")
        lines.extend(
            f"  - {r.rule_id}: {r.limitations}" for r in report.risks[:DISPLAY_CAP]
        )
    if report.rules_not_evaluated:
        lines.append(
            f"Rules not evaluated ({len(report.rules_not_evaluated)} of {len(RULES)}, "
            "data absent): " + ", ".join(report.rules_not_evaluated)
        )
    return lines


def architecture_lines(arch: Architecture) -> list[str]:
    """The architecture block as plain text lines (empty when nothing)."""
    lines: list[str] = []
    for label, items in (
        ("Components", arch.components),
        ("Workspaces", arch.workspaces),
        ("Entry points", arch.entry_points),
        ("Compose", arch.compose),
        ("Kubernetes", arch.kubernetes),
    ):
        if items:
            lines.append(f"{label}:")
            lines.extend(f"  - {item}" for item in items)
    return lines


def l3_lines(data: ReportData) -> list[str]:
    """The whole L3 section as plain lines -- the ONE function behind the
    Markdown, HTML and text renderers."""
    arch = architecture_lines(build_architecture(data))
    return [*arch, *risk_lines(evaluate_risks(data))]
