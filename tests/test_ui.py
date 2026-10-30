import subprocess
import unittest
from unittest.mock import Mock, patch

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from apt_changelog_viewer.main import (
    AptChangelogViewerApp, AptChangelogViewerWindow, _list_installed,
)


class ChangelogWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gtk.init()
        Adw.init()

    def setUp(self):
        self.app = AptChangelogViewerApp()
        self.window = AptChangelogViewerWindow(self.app)
        self.window._current_pkg = "libexample1"

    def tearDown(self):
        self.window.destroy()

    def test_package_search_matches_descriptions_case_insensitively(self):
        self.window._packages = [
            {"name": "libexample1", "version": "1.2-3", "description": "A NETWORK helper"},
            {"name": "another", "version": "2.0", "description": "Text utility"},
        ]
        self.window._search.set_text("network")
        self.window._populate_list()

        self.assertEqual(self.window._pkg_list.get_row_at_index(0)._pkg_name, "libexample1")
        self.assertIsNone(self.window._pkg_list.get_row_at_index(1))

    def test_package_search_keeps_name_and_displays_description(self):
        self.window._packages = [{
            "name": "libexample1", "version": "1.2-3", "description": "Example package description",
        }]
        self.window._populate_list()

        row = self.window._pkg_list.get_row_at_index(0)
        self.assertEqual(row._pkg_name, "libexample1")
        labels = []
        child = row.get_child().get_first_child()
        while child:
            if isinstance(child, Gtk.Label):
                labels.append(child.get_text())
            child = child.get_next_sibling()
        self.assertIn("Example package description", labels)

    def test_package_selection_starts_with_local_read_only_check(self):
        row = Mock()
        row._pkg_name = "libexample1"
        thread = Mock()

        with patch("apt_changelog_viewer.main.threading.Thread", return_value=thread) as thread_class:
            self.window._on_pkg_selected(None, row)

        kwargs = thread_class.call_args.kwargs
        self.assertEqual(kwargs["target"], self.window._load_local_changelog)
        self.assertEqual(kwargs["args"], ("libexample1",))
        thread.start.assert_called_once_with()
        self.assertFalse(self.window._fetch_button.get_sensitive())

    def test_package_scan_disables_button_until_results_arrive(self):
        thread = Mock()
        with patch("apt_changelog_viewer.main.threading.Thread", return_value=thread) as thread_class:
            self.window._on_scan(None)

        thread_class.assert_called_once()
        thread.start.assert_called_once_with()
        self.assertFalse(self.window._scan_button.get_sensitive())

        with patch.object(self.window, "_populate_list"):
            self.window._show_packages([])

        self.assertTrue(self.window._scan_button.get_sensitive())

    def test_package_scan_error_reenables_button(self):
        self.window._scan_button.set_sensitive(False)

        self.window._show_scan_error()

        self.assertTrue(self.window._scan_button.get_sensitive())

    def test_cve_and_distribution_advisories_are_highlighted_until_disabled(self):
        text = "Fixes CVE-2025-12345 and USN-7001-2."
        self.window._show_changelog("libexample1", text, "local")
        tag = self.window._security_reference_tag
        buffer = self.window._changelog_buffer
        first_match = buffer.get_iter_at_offset(text.index("CVE-2025"))
        no_match = buffer.get_iter_at_offset(0)

        self.assertIn(tag, first_match.get_tags())
        self.assertNotIn(tag, no_match.get_tags())
        self.window._highlight_security = False
        self.window._apply_security_highlights()
        self.assertNotIn(tag, buffer.get_iter_at_offset(text.index("CVE-2025")).get_tags())

    def test_stale_package_result_does_not_replace_selected_package_text(self):
        self.window._current_pkg = "libcurrent1"
        buffer = self.window._changelog_buffer
        buffer.set_text("Current package")

        self.window._show_changelog("libold1", "Old package", "remote")

        start, end = buffer.get_bounds()
        self.assertEqual(buffer.get_text(start, end, True), "Current package")

    def test_remote_request_starts_only_after_fetch_confirmation(self):
        with patch("apt_changelog_viewer.main.threading.Thread") as thread_class:
            self.window._on_fetch_changelog_response(None, "cancel", "libexample1")
            thread_class.assert_not_called()

            self.window._on_fetch_changelog_response(None, "fetch", "libexample1")

        self.assertEqual(thread_class.call_args.kwargs["target"], self.window._load_remote_changelog)
        thread_class.return_value.start.assert_called_once_with()

    def test_confirmation_discloses_network_request_and_defaults_to_cancel(self):
        with patch("apt_changelog_viewer.main.Gtk.MessageDialog") as create_dialog:
            self.window._on_fetch_changelog()

        dialog = create_dialog.return_value
        body = create_dialog.call_args.kwargs["secondary_text"]
        self.assertIn("IP address", body)
        self.assertIn("libexample1", body)
        dialog.add_button.assert_any_call("Cancel", Gtk.ResponseType.CANCEL)
        dialog.set_default_response.assert_called_once_with(Gtk.ResponseType.CANCEL)
        dialog.present.assert_called_once_with()

    def test_welcome_settings_and_about_dialogs_construct_on_supported_adwaita(self):
        self.app.window = self.window

        self.window._show_welcome()
        self.app._on_settings()
        self.app._on_about()

    def test_package_scan_error_does_not_look_like_an_empty_package_list(self):
        status = Mock()
        window = Mock()
        window._status = status

        AptChangelogViewerWindow._show_scan_error(window)

        message = status.set_text.call_args.args[0]
        self.assertIn("Could not read the installed package list", message)
        self.assertIn("dpkg-query", message)


class InstalledPackageQueryTests(unittest.TestCase):
    @patch("apt_changelog_viewer.main.subprocess.run")
    def test_lists_packages_when_dpkg_query_succeeds(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = "libexample1\t1.2-3\tExample package\n"

        self.assertEqual(_list_installed(), [{
            "name": "libexample1", "version": "1.2-3", "description": "Example package",
        }])

    @patch("apt_changelog_viewer.main.subprocess.run")
    def test_reports_nonzero_dpkg_query_exit_as_failure(self, run):
        run.return_value.returncode = 1
        run.return_value.stdout = ""

        self.assertIsNone(_list_installed())

    @patch("apt_changelog_viewer.main.subprocess.run", side_effect=FileNotFoundError)
    def test_reports_missing_dpkg_query_as_failure(self, _run):
        self.assertIsNone(_list_installed())

    @patch("apt_changelog_viewer.main.subprocess.run", side_effect=subprocess.TimeoutExpired("dpkg-query", 10))
    def test_reports_timed_out_dpkg_query_as_failure(self, _run):
        self.assertIsNone(_list_installed())


if __name__ == "__main__":
    unittest.main()
