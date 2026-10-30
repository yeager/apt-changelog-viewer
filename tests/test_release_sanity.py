import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ReleaseSanityTests(unittest.TestCase):
    def test_debian_installation_explains_the_repository_setup(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/yeager/debian-repo#setup", readme)
        self.assertIn("sudo apt install apt-changelog-viewer", readme)
        self.assertIn("https://github.com/yeager/apt-changelog-viewer/releases/latest", readme)

    def test_python_sources_do_not_call_locale_bindtextdomain(self):
        for path in ROOT.rglob("*.py"):
            if ".git" in path.parts or "build" in path.parts or "tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("locale." + "bindtextdomain(", source, str(path))

    def test_project_and_package_versions_match(self):
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        metadata_version = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)', project)
        package_init = ROOT / "src/apt_changelog_viewer" / "__init__.py"
        source_version = re.search(r'__version__\s*=\s*["\']([^"\']+)', package_init.read_text(encoding="utf-8"))
        self.assertIsNotNone(metadata_version)
        self.assertIsNotNone(source_version)
        self.assertEqual(metadata_version.group(1), source_version.group(1))

        debian_changelog = (ROOT / "debian/changelog").read_text(encoding="utf-8")
        debian_version = re.search(r"(?m)^apt-changelog-viewer \(([^)]+)\)", debian_changelog)
        self.assertIsNotNone(debian_version)
        self.assertEqual(metadata_version.group(1), debian_version.group(1).split("-", 1)[0])

    def test_generated_package_artifacts_are_not_tracked(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("build/", "dist/", "debian/files", "../*.deb", "../*.buildinfo"):
            self.assertIn(pattern, gitignore)
        self.assertFalse((ROOT / "build").exists())
        self.assertFalse((ROOT / "debian/files").exists())

if __name__ == "__main__":
    unittest.main()
