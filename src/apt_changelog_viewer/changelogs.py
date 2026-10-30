"""Read local package changelogs and fetch remote ones through APT on request."""

from __future__ import annotations

import gzip
import os
from pathlib import Path
import re
import subprocess


_PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?$")
_SECURITY_REFERENCE = re.compile(r"\b(?:CVE-\d{4}-\d{4,}|USN-\d{4}-\d+|DSA-\d+-\d+|DLA-\d+-\d+)\b", re.IGNORECASE)
MAX_CHANGELOG_CHARS = 50_000


def find_security_references(text: str) -> list[tuple[int, int]]:
    """Return character offsets of CVE and Debian/Ubuntu advisory identifiers."""
    return [match.span() for match in _SECURITY_REFERENCE.finditer(text)]


def _document_package_name(package: str) -> str | None:
    """Validate a dpkg package name and remove an optional architecture suffix."""
    if not isinstance(package, str) or not _PACKAGE_NAME.fullmatch(package):
        return None
    return package.split(":", 1)[0]


def read_local_changelog(
    package: str,
    doc_root: str | os.PathLike[str] = "/usr/share/doc",
    max_chars: int = MAX_CHANGELOG_CHARS,
) -> str | None:
    """Read a bounded portion of an installed package's compressed changelog."""
    package_name = _document_package_name(package)
    if package_name is None or isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        return None

    path = Path(doc_root) / package_name / "changelog.Debian.gz"
    try:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as changelog:
            return changelog.read(max_chars)
    except (OSError, EOFError):
        return None


def fetch_changelog_through_apt(
    package: str,
    *,
    run=subprocess.run,
    environ: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Fetch through configured APT changelog sources after explicit user consent."""
    if _document_package_name(package) is None:
        return None, "invalid-package"

    env = dict(os.environ if environ is None else environ)
    env["PAGER"] = "cat"
    env["APT_PAGER"] = "cat"
    try:
        result = run(
            ["apt-get", "changelog", package],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        return None, "apt-unavailable"
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except OSError:
        return None, "unavailable"

    if result.returncode != 0:
        return None, "fetch-failed"
    if not result.stdout.strip():
        return None, "empty-response"
    # Keep oversized remote changelogs from being queued in full for GTK to
    # render. One extra character lets the UI explain that the text was cut.
    return result.stdout[:MAX_CHANGELOG_CHARS + 1], None
