"""Ruby analyzer: RSpec/rake test + RuboCop + bundler-audit, gated on
a real Gemfile/gemspec.

Runs everything through `bundle exec` when Bundler is available so the
Gemfile.lock-pinned tool versions are used, matching how a Ruby
developer would actually invoke these locally -- never the bare
global binary, which may be a different (or absent) version.

آنالایزر Ruby: تست RSpec/rake + RuboCop + bundler-audit، فقط وقتی
Gemfile/gemspec واقعی وجود داشته باشد.

همه‌چیز را از طریق `bundle exec` اجرا می‌کند وقتی Bundler موجود باشد
تا از نسخه‌های pin‌شده‌ی Gemfile.lock استفاده شود، دقیقاً همان‌طور که
یک توسعه‌دهنده‌ی Ruby واقعاً این‌ها را محلی اجرا می‌کند -- هرگز باینری
global خام، که می‌تواند نسخه‌ای متفاوت (یا اصلاً غایب) باشد.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarand.constants import LONG_CMD_TIMEOUT
from sarand.models.results import CommandResult
from sarand.utils.command import make_command_result, run_cmd_async
from sarand.utils.logging import get_logger

logger = get_logger("analyzer.ruby")

_ENTRY_POINTS = ("main.rb", "app.rb", "lib/main.rb")

# Bundler's own error text when the gem providing a wrapped executable
# (rspec/rubocop/bundler-audit) isn't installed -- distinct from
# "bundle itself is missing", which is checked separately via
# shutil.which() before any of these commands even run.
#
# متن خطای خودِ Bundler وقتی جمی که یک اجراپذیر (rspec/rubocop/
# bundler-audit) را فراهم می‌کند نصب نشده -- این حالت از "خودِ bundle
# نصب نیست" جداست که پیش از اجرای این دستورها با shutil.which() چک
# می‌شود.
_BUNDLE_MISSING_EXEC_MARKER = "bundler: command not found:"


def _bundle_exec_missing_gem(returncode: int, output: str) -> bool:
    """True if `bundle exec` failed because the wrapped gem executable
    isn't installed (needs `bundle install`), not a real tool failure.

    درست است اگر `bundle exec` به این دلیل شکست خورده که اجراپذیرِ
    جم نصب نشده (نیاز به `bundle install` دارد)، نه یک شکست واقعی ابزار.
    """
    return returncode == 127 and _BUNDLE_MISSING_EXEC_MARKER in output


class RubyAnalyzer:
    name = "Ruby"

    def matches(self, root: Path) -> bool:
        if (root / "Gemfile").is_file():
            return True
        try:
            return any(root.glob("*.gemspec"))
        except OSError:
            return False

    def entry_points(self, root: Path) -> list[str]:
        return [ep for ep in _ENTRY_POINTS if (root / ep).is_file()]

    async def run_tests(self, root: Path) -> CommandResult | None:
        if shutil.which("bundle") is None:
            return make_command_result(
                "rspec",
                127,
                "",
                0.0,
                skipped=True,
                skip_reason="bundle (Bundler) not found in PATH",
            )

        # RSpec (spec/) is the modern default for Ruby gems/libraries;
        # Rake's `test` task (Rakefile + a Minitest-style test/ dir) is
        # the older but still common alternative. Prefer RSpec when
        # both are present since it's the more specific signal.
        #
        # RSpec (spec/) پیش‌فرض مدرن gemها/کتابخانه‌های Ruby است؛ تسک
        # `test` خودِ Rake (Rakefile + پوشه‌ی test/ به سبک Minitest)
        # جایگزین قدیمی‌تر اما همچنان رایج است. وقتی هر دو باشند، RSpec
        # ترجیح داده می‌شود چون سیگنال خاص‌تری است.
        if (root / "spec").is_dir():
            cmd = ["bundle", "exec", "rspec"]
            name = "rspec"
        elif (root / "Rakefile").is_file():
            cmd = ["bundle", "exec", "rake", "test"]
            name = "rake test"
        else:
            return make_command_result(
                "rspec",
                0,
                "",
                0.0,
                skipped=True,
                skip_reason="no spec/ directory or Rakefile found",
            )

        logger.info("Running %s", " ".join(cmd))
        rc, output, duration = await run_cmd_async(cmd, root, LONG_CMD_TIMEOUT)
        if _bundle_exec_missing_gem(rc, output):
            return make_command_result(
                name,
                rc,
                output,
                duration,
                skipped=True,
                skip_reason=(
                    f"{name.split()[0]} gem not installed -- run `bundle install`"
                ),
            )
        return make_command_result(name, rc, output, duration)

    async def run_quality(self, root: Path) -> list[CommandResult]:
        if shutil.which("bundle") is None:
            return [
                make_command_result(
                    "rubocop",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="bundle (Bundler) not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["bundle", "exec", "rubocop", "--format", "simple"], root, LONG_CMD_TIMEOUT
        )
        if _bundle_exec_missing_gem(rc, out):
            return [
                make_command_result(
                    "rubocop",
                    rc,
                    out,
                    dur,
                    skipped=True,
                    skip_reason="rubocop gem not installed -- run `bundle install`",
                )
            ]
        return [make_command_result("rubocop", rc, out, dur)]

    async def run_security(self, root: Path) -> list[CommandResult]:
        if shutil.which("bundle") is None:
            return [
                make_command_result(
                    "bundler-audit",
                    127,
                    "",
                    0.0,
                    skipped=True,
                    skip_reason="bundle (Bundler) not found in PATH",
                )
            ]
        rc, out, dur = await run_cmd_async(
            ["bundle", "exec", "bundler-audit", "check", "--update"],
            root,
            LONG_CMD_TIMEOUT,
        )
        if _bundle_exec_missing_gem(rc, out):
            return [
                make_command_result(
                    "bundler-audit",
                    rc,
                    out,
                    dur,
                    skipped=True,
                    skip_reason=(
                        "bundler-audit gem not installed -- run `bundle install`"
                    ),
                )
            ]
        return [make_command_result("bundler-audit", rc, out, dur)]
