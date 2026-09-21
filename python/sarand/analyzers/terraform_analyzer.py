"""Terraform / HCL analyzer: `terraform fmt -check` and `tflint`.

Matches on root-level `*.tf`, `*.tf.json` or `.terraform.lock.hcl`. Neither
`terraform init`, `plan` nor `apply` is ever run -- those touch providers,
state and real infrastructure. `terraform fmt -check` only reads files and
`tflint` only lints them; both are optional and skip cleanly when missing.

تحلیل‌گر Terraform / HCL: `terraform fmt -check` و `tflint`.

روی `*.tf`، `*.tf.json` یا `.terraform.lock.hcl` در ریشه match می‌شود. هرگز
`terraform init`، `plan` یا `apply` اجرا نمی‌شود -- آن‌ها به provider ها، state
و زیرساخت واقعی دست می‌زنند. `terraform fmt -check` فقط فایل می‌خواند و
`tflint` فقط lint می‌کند؛ هر دو اختیاری‌اند و نبودنشان skip تمیز می‌دهد.
"""

from __future__ import annotations

from pathlib import Path

from sarand.analyzers._tooling import existing, run_tool, top_level_files
from sarand.models.results import CommandResult


def _is_terraform(name: str) -> bool:
    return name.endswith((".tf", ".tf.json")) or name == ".terraform.lock.hcl"


class TerraformAnalyzer:
    name = "Terraform"

    def matches(self, root: Path) -> bool:
        return bool(top_level_files(root, _is_terraform))

    def entry_points(self, root: Path) -> list[str]:
        return existing(root, ("main.tf", "variables.tf", "outputs.tf", "versions.tf"))

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        return [
            await run_tool(
                root,
                "terraform fmt",
                ["terraform", "fmt", "-check", "-diff", "-no-color", "-recursive"],
            ),
            await run_tool(root, "tflint", ["tflint", "--no-color"]),
        ]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
