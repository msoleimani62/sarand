"""Known high-level problem signatures.

Since R13-A the classification lives in `core/failures.py`: a failed check is
classified from the tool that ran and from strong evidence, and the known-issue
sentences are derived from that classification. This module keeps the old public
name `detect_known_issues` for existing callers.
از R13-A طبقه‌بندی در `core/failures.py` است؛ این ماژول فقط نام قدیمی را نگه
می‌دارد.
"""

from __future__ import annotations

from sarand.core.failures import detect_known_issues

__all__ = ["detect_known_issues"]
