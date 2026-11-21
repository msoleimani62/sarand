"""Which distributions ship an import name (R14-A3, criterion 4).

An import name and the name of the distribution that provides it are two different
things: `import yaml` is provided by the distribution `PyYAML`, `import PIL` by
`Pillow`. A manifest declares distributions, so matching an import to a declaration
by name alone leaves `yaml` unmatched although `PyYAML` is declared.

This module is an **explicit, short table** of pairs that are well established, and
nothing else:

- an entry maps one import name to *every* distribution known to ship it besides the
  distribution of the same name (which is always tried first), so a name with several
  providers (`cv2`) keeps all of them and no provider is picked;
- an import name that is not in the table is matched only by name, as before, and
  stays `external_unmatched` when nothing carries that name: the table is not
  complete and nothing is guessed from similarity;
- installed packages are never read (no `top_level.txt`, no `RECORD`), so the result
  is a fact about declarations, not about an environment.

A declaration found through this table is `probable`, not `definite`: the pair comes
from this table, not from the text of the project.

جدولی صریح و کوتاه از نام import و distributionهایی که آن را عرضه می‌کنند؛ حدسی در کار نیست.
"""

from __future__ import annotations

# Import name (case-sensitive, as written in the source) -> PEP 503 normalised names of
# every distribution that ships it. Keep the table sorted by import name.
# نام import -> نام نرمال‌شده‌ی همه‌ی distributionهایی که آن را عرضه می‌کنند.
PROVIDED_BY: dict[str, tuple[str, ...]] = {
    "Crypto": ("pycryptodome", "pycrypto"),
    "Cryptodome": ("pycryptodomex",),
    "MySQLdb": ("mysql-python", "mysqlclient"),
    "OpenSSL": ("pyopenssl",),
    "PIL": ("pillow", "pillow-simd"),
    "attr": ("attrs",),
    "bs4": ("beautifulsoup4",),
    "cv2": (
        "opencv-contrib-python",
        "opencv-contrib-python-headless",
        "opencv-python",
        "opencv-python-headless",
    ),
    "dateutil": ("python-dateutil",),
    "docx": ("python-docx",),
    "dotenv": ("python-dotenv",),
    "gi": ("pygobject",),
    "git": ("gitpython",),
    "jwt": ("pyjwt",),
    "magic": ("python-magic", "file-magic"),
    "pkg_resources": ("setuptools",),
    "psycopg2": ("psycopg2-binary",),
    "serial": ("pyserial",),
    "skimage": ("scikit-image",),
    "sklearn": ("scikit-learn",),
    "usb": ("pyusb",),
    "wx": ("wxpython",),
    "yaml": ("pyyaml",),
    "zmq": ("pyzmq",),
}


def providers(import_name: str) -> tuple[str, ...]:
    """The distributions known to ship `import_name` (empty when it is not in the
    table). The lookup is by the exact import name."""
    return PROVIDED_BY.get(import_name, ())
