import gzip
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from apt_changelog_viewer.changelogs import fetch_changelog_through_apt, find_security_references, read_local_changelog


class LocalChangelogTests(unittest.TestCase):
    def test_reads_installed_compressed_changelog_for_arch_qualified_package(self):
        with tempfile.TemporaryDirectory() as directory:
            changelog_path = Path(directory) / "libexample1" / "changelog.Debian.gz"
            changelog_path.parent.mkdir()
            with gzip.open(changelog_path, "wt", encoding="utf-8") as changelog:
                changelog.write("libexample1 (1.2-3) stable; urgency=medium\n")

            text = read_local_changelog("libexample1:amd64", directory)

        self.assertIn("1.2-3", text)

    def test_returns_none_when_local_changelog_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(read_local_changelog("libexample1", directory))

    def test_rejects_path_traversal_package_names(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(read_local_changelog("../../etc/passwd", directory))


class SecurityReferenceTests(unittest.TestCase):
    def test_finds_cve_and_distribution_advisory_references(self):
        text = "Fixes CVE-2025-12345, USN-7001-2, DSA-5678-1 and DLA-123-4."
        spans = find_security_references(text)

        self.assertEqual([text[start:end] for start, end in spans], [
            "CVE-2025-12345", "USN-7001-2", "DSA-5678-1", "DLA-123-4",
        ])

    def test_ignores_unrelated_numbers_and_malformed_references(self):
        self.assertEqual(find_security_references("CVE-2025-123 USN-7 DSA-1.2 package 42"), [])


class RemoteChangelogTests(unittest.TestCase):
    def test_fetches_only_through_apt_with_pager_disabled(self):
        run = Mock(return_value=Mock(returncode=0, stdout="Package changelog", stderr=""))

        text, error = fetch_changelog_through_apt(
            "libexample1", run=run, environ={"PATH": "/usr/bin"},
        )

        self.assertEqual((text, error), ("Package changelog", None))
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["apt-get", "changelog", "libexample1"])
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(kwargs["env"]["APT_PAGER"], "cat")
        self.assertEqual(kwargs["env"]["PAGER"], "cat")

    def test_rejects_invalid_package_without_running_apt(self):
        run = Mock()

        self.assertEqual(fetch_changelog_through_apt("../bad", run=run), (None, "invalid-package"))
        run.assert_not_called()

    def test_reports_missing_apt(self):
        run = Mock(side_effect=FileNotFoundError)

        self.assertEqual(fetch_changelog_through_apt("libexample1", run=run), (None, "apt-unavailable"))

    def test_reports_timeout(self):
        run = Mock(side_effect=subprocess.TimeoutExpired("apt-get", 30))

        self.assertEqual(fetch_changelog_through_apt("libexample1", run=run), (None, "timeout"))

    def test_reports_apt_failure_and_empty_response(self):
        failed = Mock(return_value=Mock(returncode=100, stdout="", stderr="network error"))
        empty = Mock(return_value=Mock(returncode=0, stdout="  ", stderr=""))

        self.assertEqual(fetch_changelog_through_apt("libexample1", run=failed), (None, "fetch-failed"))
        self.assertEqual(fetch_changelog_through_apt("libexample1", run=empty), (None, "empty-response"))


if __name__ == "__main__":
    unittest.main()
