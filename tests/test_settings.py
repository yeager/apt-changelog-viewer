import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apt_changelog_viewer import settings


class SettingsStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.settings_directory = Path(self.temporary_directory.name)
        self.settings_file = self.settings_directory / "settings.json"
        self.directory_patch = patch.object(settings, "SETTINGS_DIR", str(self.settings_directory))
        self.file_patch = patch.object(settings, "SETTINGS_FILE", str(self.settings_file))
        self.directory_patch.start()
        self.file_patch.start()
        self.addCleanup(self.file_patch.stop)
        self.addCleanup(self.directory_patch.stop)

    def test_missing_file_uses_defaults(self):
        self.assertEqual(settings.load_settings(), settings.DEFAULT_SETTINGS)

    def test_corrupt_json_uses_defaults(self):
        self.settings_file.write_text("{broken", encoding="utf-8")
        self.assertEqual(settings.load_settings(), settings.DEFAULT_SETTINGS)

    def test_non_object_json_uses_defaults(self):
        self.settings_file.write_text('["unexpected"]', encoding="utf-8")
        self.assertEqual(settings.load_settings(), settings.DEFAULT_SETTINGS)

    def test_non_boolean_preferences_use_defaults_and_keep_other_keys(self):
        self.settings_file.write_text(
            '{"welcome_shown": "yes", "highlight_security_updates": 0, "future": 7}',
            encoding="utf-8",
        )
        self.assertEqual(settings.load_settings(), {
            **settings.DEFAULT_SETTINGS,
            "future": 7,
        })

    def test_invalid_utf8_uses_defaults(self):
        self.settings_file.write_bytes(b"\xff\xfe")
        self.assertEqual(settings.load_settings(), settings.DEFAULT_SETTINGS)

    def test_settings_are_saved_atomically_as_utf8(self):
        values = {"welcome_shown": True, "label": "svenska"}
        self.assertTrue(settings.save_settings(values))
        self.assertEqual(json.loads(self.settings_file.read_text(encoding="utf-8")), values)
        self.assertEqual(list(self.settings_directory.glob(".settings-*.tmp")), [])

    def test_failed_replace_preserves_previous_settings(self):
        previous = '{"welcome_shown": false}'
        self.settings_file.write_text(previous, encoding="utf-8")
        with patch.object(settings.os, "replace", side_effect=OSError("read-only")):
            self.assertFalse(settings.save_settings({"welcome_shown": True}))
        self.assertEqual(self.settings_file.read_text(encoding="utf-8"), previous)
        self.assertEqual(list(self.settings_directory.glob(".settings-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
