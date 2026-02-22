"""Apt Changelog Viewer — View changelogs for installed packages."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, Pango

import gettext
import locale
import os
import sys
import json
import datetime
import threading
import subprocess
import re
from apt_changelog_viewer.accessibility import AccessibilityManager

LOCALE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "po")
if not os.path.isdir(LOCALE_DIR):
    LOCALE_DIR = "/usr/share/locale"
locale.bindtextdomain("apt-changelog-viewer", LOCALE_DIR)
gettext.bindtextdomain("apt-changelog-viewer", LOCALE_DIR)
gettext.textdomain("apt-changelog-viewer")
_ = gettext.gettext

APP_ID = "se.danielnylander.apt.changelog.viewer"
SETTINGS_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "apt-changelog-viewer"
)
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


def _load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {"welcome_shown": False}


def _save_settings(s):
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)



def _list_installed():
    """List installed packages."""
    pkgs = []
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f", "${Package}\t${Version}\t${Description}\n"],
                          capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) >= 2:
                pkgs.append({"name": parts[0], "version": parts[1],
                            "description": parts[2] if len(parts) > 2 else ""})
    except:
        pass
    return pkgs


def _get_changelog(package):
    """Get changelog for a package."""
    try:
        r = subprocess.run(["apt-get", "changelog", package, "--print-uris"],
                          capture_output=True, text=True, timeout=10)
        if r.stdout.strip():
            import urllib.request
            url = r.stdout.strip().split("'")[1] if "'" in r.stdout else r.stdout.strip()
            with urllib.request.urlopen(url, timeout=10) as resp:
                return resp.read().decode(errors="replace")
    except:
        pass
    # Fallback: local changelog
    path = f"/usr/share/doc/{package}/changelog.Debian.gz"
    if os.path.exists(path):
        import gzip
        with gzip.open(path, "rt", errors="replace") as f:
            return f.read()
    return _("No changelog available")



class AptChangelogViewerWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("Apt Changelog Viewer"), default_width=1000, default_height=700)
        self.settings = _load_settings()
        
        self._packages = []
        self._current_pkg = None

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header
        headerbar = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title=_("Apt Changelog Viewer"), subtitle="")
        headerbar.set_title_widget(title_widget)
        self._title_widget = title_widget

        
        scan_btn = Gtk.Button(icon_name="system-search-symbolic", tooltip_text=_("Scan installed packages"))
        scan_btn.connect("clicked", self._on_scan)
        headerbar.pack_start(scan_btn)
        
        self._search = Gtk.SearchEntry(placeholder_text=_("Search packages..."))
        self._search.set_size_request(200, -1)
        self._search.connect("search-changed", self._on_search)
        headerbar.pack_start(self._search)

        # Menu
        menu = Gio.Menu()
        menu.append(_("Settings"), "app.settings")
        menu.append(_("Copy Debug Info"), "app.copy-debug")
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About Apt Changelog Viewer"), "app.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        headerbar.pack_end(menu_btn)

        main_box.append(headerbar)

        
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_size_request(350, -1)
        self._pkg_list = Gtk.ListBox()
        self._pkg_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._pkg_list.connect("row-selected", self._on_pkg_selected)
        left_scroll.set_child(self._pkg_list)
        paned.set_start_child(left_scroll)
        
        right_scroll = Gtk.ScrolledWindow()
        self._changelog_view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self._changelog_view.set_top_margin(8)
        self._changelog_view.set_left_margin(8)
        right_scroll.set_child(self._changelog_view)
        paned.set_end_child(right_scroll)
        paned.set_position(380)
        
        main_box.append(paned)

        # Status bar
        self._status = Gtk.Label(label=_("Ready"), xalign=0)
        self._status.set_margin_start(12)
        self._status.set_margin_end(12)
        self._status.set_margin_top(4)
        self._status.set_margin_bottom(4)
        self._status.add_css_class("dim-label")
        main_box.append(self._status)

        self.set_content(main_box)

        if not self.settings.get("welcome_shown"):
            GLib.idle_add(self._show_welcome)

    def _show_welcome(self):
        dialog = Adw.Dialog()
        dialog.set_title(_("Welcome"))
        dialog.set_content_width(420)
        dialog.set_content_height(480)

        page = Adw.StatusPage()
        page.set_icon_name("text-x-changelog-symbolic")
        page.set_title(_("Welcome to Apt Changelog Viewer"))
        page.set_description(_("Browse package changelogs.\n\n"
            "✓ View changelogs for installed packages\n"
            "✓ Security update highlighting\n"
            "✓ Search installed packages\n"
            "✓ Quick package info\n"
            "✓ Mark important updates"))

        btn = Gtk.Button(label=_("Get Started"))
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(12)
        btn.connect("clicked", self._on_welcome_close, dialog)
        page.set_child(btn)

        box = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_show_title(False)
        box.add_top_bar(hb)
        box.set_content(page)
        dialog.set_child(box)
        dialog.present(self)

    def _on_welcome_close(self, btn, dialog):
        self.settings["welcome_shown"] = True
        _save_settings(self.settings)
        dialog.close()

    
    def _on_scan(self, btn):
        self._status.set_text(_("Scanning installed packages..."))
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        pkgs = _list_installed()
        GLib.idle_add(self._show_packages, pkgs)

    def _show_packages(self, pkgs):
        self._packages = pkgs
        self._populate_list()

    def _populate_list(self):
        while True:
            row = self._pkg_list.get_row_at_index(0)
            if row is None:
                break
            self._pkg_list.remove(row)
        
        search = self._search.get_text().lower()
        count = 0
        for pkg in self._packages:
            if search and search not in pkg["name"].lower():
                continue
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            name_label = Gtk.Label(label=pkg["name"], xalign=0, ellipsize=Pango.EllipsizeMode.END)
            box.append(name_label)
            ver_label = Gtk.Label(label=pkg["version"], xalign=0)
            ver_label.add_css_class("dim-label")
            ver_label.add_css_class("caption")
            box.append(ver_label)
            row.set_child(box)
            row._pkg_name = pkg["name"]
            self._pkg_list.append(row)
            count += 1
            if count > 500:
                break
        
        self._status.set_text(_("%(count)d packages") % {"count": count})

    def _on_search(self, entry):
        self._populate_list()

    def _on_pkg_selected(self, listbox, row):
        if row is None:
            return
        pkg = row._pkg_name
        self._current_pkg = pkg
        self._title_widget.set_subtitle(pkg)
        self._changelog_view.get_buffer().set_text(_("Loading changelog..."))
        threading.Thread(target=self._load_changelog, args=(pkg,), daemon=True).start()

    def _load_changelog(self, pkg):
        text = _get_changelog(pkg)
        GLib.idle_add(self._show_changelog, text)

    def _show_changelog(self, text):
        self._changelog_view.get_buffer().set_text(text[:50000])


class AptChangelogViewerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None

        for name, callback in [
            ("settings", self._on_settings),
            ("copy-debug", self._on_copy_debug),
            ("shortcuts", self._on_shortcuts),
            ("about", self._on_about),
            ("quit", self._on_quit),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        self.set_accels_for_action("app.shortcuts", ["<Ctrl>slash"])

    def do_activate(self):
        if not self.window:
            self.window = AptChangelogViewerWindow(self)
        self.window.present()

    def _on_settings(self, *_args):
        if not self.window:
            return
        dialog = Adw.PreferencesDialog()
        dialog.set_title(_("Settings"))
        page = Adw.PreferencesPage()
        
        group = Adw.PreferencesGroup(title=_("Display"))
        row = Adw.SwitchRow(title=_("Highlight security updates"))
        row.set_active(True)
        group.add(row)
        page.add(group)
        dialog.add(page)
        dialog.present(self.window)

    def _on_copy_debug(self, *_args):
        if not self.window:
            return
        from . import __version__
        info = (
            f"Apt Changelog Viewer {__version__}\n"
            f"Python {sys.version}\n"
            f"GTK {Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}\n"
            f"Adw {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}\n"
            f"OS: {os.uname().sysname} {os.uname().release}\n"
        )
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(info)
        self.window._status.set_text(_("Debug info copied"))

    def _on_shortcuts(self, *_args):
        if self.window:
            dialog = Gtk.ShortcutsWindow(transient_for=self.window)
            section = Gtk.ShortcutsSection(visible=True)
            group = Gtk.ShortcutsGroup(title=_("General"), visible=True)
            for accel, title in [
                ("<Ctrl>q", _("Quit")),
                ("<Ctrl>slash", _("Keyboard shortcuts")),
            ]:
                group.append(Gtk.ShortcutsShortcut(accelerator=accel, title=title, visible=True))
            section.append(group)
            dialog.append(section)
            dialog.present()

    def _on_about(self, *_args):
        from . import __version__
        dialog = Adw.AboutDialog(
            application_name=_("Apt Changelog Viewer"),
            application_icon="text-x-changelog-symbolic",
            version=__version__,
            developer_name="Daniel Nylander",
            website="https://github.com/yeager/apt-changelog-viewer",
            license_type=Gtk.License.GPL_3_0,
            issue_url="https://github.com/yeager/apt-changelog-viewer/issues",
            comments=_("View changelogs for installed packages. Get notified about security updates."),
        )
        dialog.present(self.window)

    def _on_quit(self, *_args):
        self.quit()


def main():
    app = AptChangelogViewerApp()
    app.run(sys.argv)


# --- Session restore ---
import json as _json
import os as _os

def _save_session(window, app_name):
    config_dir = _os.path.join(_os.path.expanduser('~'), '.config', app_name)
    _os.makedirs(config_dir, exist_ok=True)
    state = {'width': window.get_width(), 'height': window.get_height(),
             'maximized': window.is_maximized()}
    try:
        with open(_os.path.join(config_dir, 'session.json'), 'w') as f:
            _json.dump(state, f)
    except OSError:
        pass

def _restore_session(window, app_name):
    path = _os.path.join(_os.path.expanduser('~'), '.config', app_name, 'session.json')
    try:
        with open(path) as f:
            state = _json.load(f)
        window.set_default_size(state.get('width', 800), state.get('height', 600))
        if state.get('maximized'):
            window.maximize()
    except (FileNotFoundError, _json.JSONDecodeError, OSError):
        pass


# --- Fullscreen toggle (F11) ---
def _setup_fullscreen(window, app):
    """Add F11 fullscreen toggle."""
    from gi.repository import Gio
    if not app.lookup_action('toggle-fullscreen'):
        action = Gio.SimpleAction.new('toggle-fullscreen', None)
        action.connect('activate', lambda a, p: (
            window.unfullscreen() if window.is_fullscreen() else window.fullscreen()
        ))
        app.add_action(action)
        app.set_accels_for_action('app.toggle-fullscreen', ['F11'])


# --- Plugin system ---
import importlib.util
import os as _pos

def _load_plugins(app_name):
    """Load plugins from ~/.config/<app>/plugins/."""
    plugin_dir = _pos.path.join(_pos.path.expanduser('~'), '.config', app_name, 'plugins')
    plugins = []
    if not _pos.path.isdir(plugin_dir):
        return plugins
    for fname in sorted(_pos.listdir(plugin_dir)):
        if fname.endswith('.py') and not fname.startswith('_'):
            path = _pos.path.join(plugin_dir, fname)
            try:
                spec = importlib.util.spec_from_file_location(fname[:-3], path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                plugins.append(mod)
            except Exception as e:
                print(f"Plugin {fname}: {e}")
    return plugins
