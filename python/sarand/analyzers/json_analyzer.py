"""JSON analyzer: jsonlint when available, otherwise a built-in
syntax-only validation via Python's own `json` module -- gated on a
top-level *.json file.

The stdlib fallback is a deliberate departure from every other
analyzer's "skip cleanly if the tool binary is missing" rule: JSON
syntax validation needs no external tool at all (Python already has
one built in), so skipping instead of validating would be strictly
worse for no reason. jsonlint is still preferred when present since it
also catches style issues, not just parse errors.

A format analyzer, not a language analyzer: no run_tests, and no
run_security (no broadly standard JSON vulnerability-audit tool) --
same honest-empty shape as YamlAnalyzer/CssAnalyzer.

آنالایزر JSON: jsonlint در صورت وجود، وگرنه اعتبارسنجیِ صرفاً-syntax
داخلی با ماژول `json` خودِ Python -- فقط وقتی یک فایل *.json سطح-ریشه
وجود داشته باشد.

fallback به stdlib یک انحراف عمدی از قاعده‌ی «اگر باینری ابزار نبود
تمیز skip کن» در بقیه‌ی آنالایزرهاست: اعتبارسنجی syntax JSON اصلاً به
ابزار خارجی نیاز ندارد (Python از قبل یکی داخلش دارد)، پس skip کردن
به‌جای اعتبارسنجی، بدون دلیل، قطعاً بدتر است. jsonlint وقتی موجود باشد
همچنان ترجیح داده می‌شود چون مسائل سبکی را هم می‌گیرد، نه فقط خطای parse.

یک آنالایزر فرمت است، نه زبان: بدون run_tests، و بدون run_security
(بدون ابزار audit آسیب‌پذیریِ به‌طور گسترده استاندارد برای JSON) -- همان
شکل خالیِ صادقانه‌ی YamlAnalyzer/CssAnalyzer.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.json")

_ENTRY_POINTS = ("package.json", "tsconfig.json", "composer.json")


def _top_level_json_files(root: Path) -> list[Path]:
    try:
        return sorted(
            p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".json"
        )
    except OSError:
        return []


def _validate_with_stdlib(files: list[Path]) -> CommandResult:
    errors: list[str] = []
    for path in files:
        try:
            json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        return make_command_result("json syntax check", 1, "\n".join(errors), 0.0)
    return make_command_result(
        "json syntax check", 0, f"{len(files)} file(s) valid", 0.0
    )


class JsonAnalyzer:
    name = "JSON"

    def matches(self, root: Path) -> bool:
        return bool(_top_level_json_files(root))

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        return None

    async def run_quality(self, root: Path) -> list[CommandResult]:
        files = _top_level_json_files(root)
        jsonlint = shutil.which("jsonlint")
        if jsonlint is None:
            return [_validate_with_stdlib(files)]
        rc, out, dur = await run_cmd_async(
            [jsonlint, "-q", *(str(p.name) for p in files)], root, LONG_CMD_TIMEOUT
        )
        return [make_command_result("jsonlint", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        return []
