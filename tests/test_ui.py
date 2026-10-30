import unittest
from unittest.mock import Mock, patch

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from apt_changelog_viewer.main import AptChangelogViewerApp, AptChangelogViewerWindow


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


if __name__ == "__main__":
    unittest.main()
