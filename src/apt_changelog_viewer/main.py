"""Apt Changelog Viewer — View changelogs for installed packages."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, Pango

import gettext
import os
import sys
import threading
import subprocess
from apt_changelog_viewer.settings import load_settings as _load_settings, save_settings as _save_settings
from apt_changelog_viewer.changelogs import MAX_CHANGELOG_CHARS, fetch_changelog_through_apt, find_security_references, read_local_changelog

LOCALE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "po")
if not os.path.isdir(LOCALE_DIR):
    LOCALE_DIR = "/usr/share/locale"
gettext.bindtextdomain("apt-changelog-viewer", LOCALE_DIR)
gettext.textdomain("apt-changelog-viewer")
_ = gettext.gettext

APP_ID = "se.danielnylander.apt.changelog.viewer"
def _list_installed():
    """List installed packages, or return None when dpkg-query fails."""
    pkgs = []
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f", "${Package}\t${Version}\t${Description}\n"],
                          capture_output=True, text=True, timeout=10, check=False)
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) >= 2:
                pkgs.append({"name": parts[0], "version": parts[1],
                            "description": parts[2] if len(parts) > 2 else ""})
    except (OSError, subprocess.SubprocessError):
        return None
    return pkgs


class AptChangelogViewerWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=_("Apt Changelog Viewer"), default_width=1000, default_height=700)
        self.settings = _load_settings()
        self._highlight_security = self.settings.get("highlight_security_updates", True)
        self._current_changelog = ""
        
        self._packages = []
        self._current_pkg = None

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header
        headerbar = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title=_("Apt Changelog Viewer"), subtitle="")
        headerbar.set_title_widget(title_widget)
        self._title_widget = title_widget

        
        self._scan_button = Gtk.Button(icon_name="system-search-symbolic", tooltip_text=_("Scan installed packages"))
        self._scan_button.connect("clicked", self._on_scan)
        headerbar.pack_start(self._scan_button)
        
        self._search = Gtk.SearchEntry(placeholder_text=_("Search packages or descriptions..."))
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

        self._fetch_button = Gtk.Button(label=_("Fetch online changelog"), sensitive=False)
        self._fetch_button.connect("clicked", self._on_fetch_changelog)
        headerbar.pack_end(self._fetch_button)

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
        self._changelog_buffer = self._changelog_view.get_buffer()
        self._security_reference_tag = self._changelog_buffer.create_tag(
            "security-reference", weight=Pango.Weight.BOLD, underline=Pango.Underline.SINGLE,
        )
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
        uses_adaptive_dialog = hasattr(Adw, "Dialog")
        if uses_adaptive_dialog:
            dialog = Adw.Dialog()
            dialog.set_title(_("Welcome"))
            dialog.set_content_width(420)
            dialog.set_content_height(480)
        else:
            dialog = Adw.Window(
                transient_for=self, modal=True, title=_("Welcome"),
                default_width=420, default_height=480,
            )

        page = Adw.StatusPage()
        page.set_icon_name("text-x-changelog-symbolic")
        page.set_title(_("Welcome to Apt Changelog Viewer"))
        page.set_description(_("Browse package changelogs.\n\n"
            "✓ Read local changelogs without a network request\n"
            "✓ Fetch remote changelogs only after confirmation\n"
            "✓ Highlight CVE and distribution advisory references\n"
            "✓ Search installed packages"))

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
        if uses_adaptive_dialog:
            dialog.set_child(box)
            dialog.present(self)
        else:
            dialog.set_content(box)
            dialog.present()

    def _on_welcome_close(self, btn, dialog):
        self.settings["welcome_shown"] = True
        _save_settings(self.settings)
        dialog.close()

    
    def _on_scan(self, btn):
        self._scan_button.set_sensitive(False)
        self._status.set_text(_("Scanning installed packages..."))
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        pkgs = _list_installed()
        if pkgs is None:
            GLib.idle_add(self._show_scan_error)
            return
        GLib.idle_add(self._show_packages, pkgs)

    def _show_scan_error(self):
        self._scan_button.set_sensitive(True)
        self._status.set_text(_("Could not read the installed package list. Check that dpkg-query is available and try again."))
        return GLib.SOURCE_REMOVE

    def _show_packages(self, pkgs):
        self._scan_button.set_sensitive(True)
        self._packages = pkgs
        self._populate_list()

    def _populate_list(self):
        while True:
            row = self._pkg_list.get_row_at_index(0)
            if row is None:
                break
            self._pkg_list.remove(row)
        
        search = self._search.get_text().casefold().strip()
        count = 0
        for pkg in self._packages:
            description = pkg.get("description", "")
            searchable_text = f"{pkg['name']} {description}".casefold()
            if search and search not in searchable_text:
                continue
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            name_label = Gtk.Label(label=pkg["name"], xalign=0, ellipsize=Pango.EllipsizeMode.END)
            box.append(name_label)
            if description:
                description_label = Gtk.Label(
                    label=description, xalign=0, wrap=True, lines=2,
                    ellipsize=Pango.EllipsizeMode.END,
                )
                description_label.add_css_class("dim-label")
                description_label.add_css_class("caption")
                box.append(description_label)
            ver_label = Gtk.Label(label=pkg["version"], xalign=0)
            ver_label.add_css_class("dim-label")
            ver_label.add_css_class("caption")
            box.append(ver_label)
            row.set_child(box)
            row._pkg_name = pkg["name"]
            self._pkg_list.append(row)
            count += 1
            if count >= 500:
                break
        
        self._status.set_text(_("%(count)d packages") % {"count": count})

    def _on_search(self, entry):
        self._populate_list()

    def _on_pkg_selected(self, listbox, row):
        if row is None:
            return
        pkg = row._pkg_name
        self._current_pkg = pkg
        self._fetch_button.set_sensitive(False)
        self._title_widget.set_subtitle(pkg)
        self._status.set_text(_("Checking for a local changelog…"))
        self._changelog_view.get_buffer().set_text(_("Reading the local changelog…"))
        threading.Thread(target=self._load_local_changelog, args=(pkg,), daemon=True).start()

    def _load_local_changelog(self, pkg):
        text = read_local_changelog(pkg, max_chars=MAX_CHANGELOG_CHARS + 1)
        if text is None:
            display_text = _("No local changelog is installed. Choose Fetch online changelog to request one from the APT-configured source.")
        else:
            display_text = text
        GLib.idle_add(self._show_changelog, pkg, display_text, "local", text is not None)

    def _show_changelog(self, pkg, text, source, has_local=True):
        if pkg != self._current_pkg:
            return GLib.SOURCE_REMOVE
        self._fetch_button.set_sensitive(True)
        self._current_changelog = text[:MAX_CHANGELOG_CHARS]
        if len(text) > MAX_CHANGELOG_CHARS:
            self._current_changelog += "\n\n" + _(
                "Changelog shortened; only the first 50,000 characters are shown."
            )
        self._changelog_buffer.set_text(self._current_changelog)
        self._apply_security_highlights()
        if source == "remote":
            self._status.set_text(_("Online changelog loaded"))
        elif has_local:
            self._status.set_text(_("Local changelog loaded"))
        else:
            self._status.set_text(_("No local changelog found"))
        return GLib.SOURCE_REMOVE

    def _apply_security_highlights(self):
        start, end = self._changelog_buffer.get_bounds()
        self._changelog_buffer.remove_tag(self._security_reference_tag, start, end)
        if not self._highlight_security:
            return
        for offset, limit in find_security_references(self._current_changelog):
            self._changelog_buffer.apply_tag(
                self._security_reference_tag,
                self._changelog_buffer.get_iter_at_offset(offset),
                self._changelog_buffer.get_iter_at_offset(limit),
            )

    def _on_fetch_changelog(self, *_args):
        pkg = self._current_pkg
        if not pkg:
            return
        self._fetch_button.set_sensitive(False)
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=_("Fetch this changelog from your configured APT source?"),
            secondary_text=_("APT will contact the changelog server configured by your software sources to request %(package)s. That server can see your IP address and the package name. No packages will be installed. Continue?") % {"package": pkg},
        )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Fetch changelog"), Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.connect("response", self._on_fetch_dialog_response, pkg)
        dialog.present()

    def _on_fetch_dialog_response(self, _dialog, response, pkg):
        selected = "fetch" if response == Gtk.ResponseType.ACCEPT else "cancel"
        self._on_fetch_changelog_response(_dialog, selected, pkg)

    def _on_fetch_changelog_response(self, _dialog, response, pkg):
        if pkg != self._current_pkg:
            return
        if response != "fetch":
            self._fetch_button.set_sensitive(True)
            return
        self._fetch_button.set_sensitive(False)
        self._status.set_text(_("Fetching changelog from the configured APT source…"))
        threading.Thread(target=self._load_remote_changelog, args=(pkg,), daemon=True).start()

    def _load_remote_changelog(self, pkg):
        text, error = fetch_changelog_through_apt(pkg)
        GLib.idle_add(self._show_remote_changelog, pkg, text, error)

    def _show_remote_changelog(self, pkg, text, error):
        if pkg != self._current_pkg:
            return GLib.SOURCE_REMOVE
        self._fetch_button.set_sensitive(True)
        if text is not None:
            self._show_changelog(pkg, text, "remote")
        else:
            messages = {
                "apt-unavailable": _("APT tools are not available on this system."),
                "timeout": _("The changelog request timed out. Your local changelog, if available, is still shown."),
                "empty-response": _("The APT source returned an empty changelog."),
                "invalid-package": _("The package name is not valid."),
            }
            self._status.set_text(messages.get(error, _("Could not fetch the changelog. Check your configured software sources or network connection.")))
        return GLib.SOURCE_REMOVE


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
        uses_preferences_dialog = hasattr(Adw, "PreferencesDialog")
        if uses_preferences_dialog:
            dialog = Adw.PreferencesDialog()
            dialog.set_title(_("Settings"))
        else:
            dialog = Adw.PreferencesWindow(
                transient_for=self.window, modal=True, title=_("Settings"),
            )
        page = Adw.PreferencesPage()
        
        group = Adw.PreferencesGroup(title=_("Display"))
        row = Adw.SwitchRow(title=_("Highlight security references"))
        row.set_active(self.window._highlight_security)
        row.connect("notify::active", self._on_security_highlighting_changed)
        group.add(row)
        page.add(group)
        dialog.add(page)
        if uses_preferences_dialog:
            dialog.present(self.window)
        else:
            dialog.present()

    def _on_security_highlighting_changed(self, row, _property):
        if not self.window:
            return
        self.window._highlight_security = row.get_active()
        self.window.settings["highlight_security_updates"] = self.window._highlight_security
        _save_settings(self.window.settings)
        self.window._apply_security_highlights()

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
        uses_about_dialog = hasattr(Adw, "AboutDialog")
        about_window = Adw.AboutDialog if uses_about_dialog else Adw.AboutWindow
        dialog = about_window(
            application_name=_("Apt Changelog Viewer"),
            application_icon="text-x-changelog-symbolic",
            version=__version__,
            developer_name="Daniel Nylander",
            website="https://github.com/yeager/apt-changelog-viewer",
            license_type=Gtk.License.GPL_3_0,
            issue_url="https://github.com/yeager/apt-changelog-viewer/issues",
            comments=_("View package changelogs and highlight CVE and distribution security advisory references."),
        )
        if uses_about_dialog:
            dialog.present(self.window)
        else:
            dialog.present()

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
