"""Clipboard transport: OSC52 first (works with no display server --
the only mechanism that works inside a rootless Android proot), then
subprocess-based tools as a fallback for machines with a graphical
session.

Unchanged from the original scripts/paste_chunks.py logic; only moved
here so the RC package has one file per responsibility.

انتقال کلیپ‌بورد: اول OSC52 (بدون نیاز به display server کار می‌کند --
تنها مکانیزمی که داخل یک proot اندروید بدون روت کار می‌کند)، سپس
ابزارهای مبتنی بر subprocess به‌عنوان جایگزین برای دستگاه‌هایی که نشست
گرافیکی دارند.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess

# Raw text size ceiling for OSC52, applied BEFORE base64 -- not the
# final escape-sequence length. Empirically tested and proven reliable
# on this specific hardware/terminal combo (non-rooted Android,
# Termux/Kali NetHunter proot, no X11/Wayland session -- OSC52 is the
# only clipboard mechanism that works at all here, since it operates
# purely through terminal output rather than talking to a display
# server or an external clipboard tool). Base64 inflates ~4000 raw
# bytes to ~5336, well inside terminals' typical OSC52 buffer limits;
# 6000 raw was the tested ceiling, kept here as a hard safety check in
# case a single long line ever pushes one chunk above the normal
# CHUNK_SIZE cap.
OSC52_MAX_BYTES = 6000


def _osc52_copy(text: str) -> bool:
    """Set the system clipboard via the OSC52 terminal escape sequence.

    Works purely through terminal output -- no external clipboard tool
    and no X11/Wayland session needed. On a non-rooted Android phone
    running Termux/Kali NetHunter proot, this is the *only* reliable
    clipboard mechanism (xclip/xsel/wl-copy have no display server to
    talk to; termux-clipboard-set needs Termux:API, which may not be
    reachable from inside a proot). Tried first for exactly that
    reason; the subprocess-based tools below remain as a fallback for
    running this on a machine that does have a graphical session.
    """
    payload = text.encode("utf-8")
    if len(payload) > OSC52_MAX_BYTES:
        return False

    b64 = base64.b64encode(payload).decode("ascii")
    sequence = f"\x1b]52;c;{b64}\x07"

    if os.environ.get("TMUX"):
        sequence = "\x1bPtmux;" + sequence.replace("\x1b", "\x1b\x1b") + "\x1b\\"
    elif os.environ.get("STY"):
        sequence = "\x1bP" + sequence + "\x1b\\"

    try:
        with open("/dev/tty", "w") as tty:
            tty.write(sequence)
            tty.flush()
        return True
    except OSError:
        return False


def clipboard_copy(text: str) -> bool:
    if _osc52_copy(text):
        return True

    commands = (
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["termux-clipboard-set"],
        ["wl-copy"],
    )
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            result = subprocess.run(
                command,
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return True
    return False
