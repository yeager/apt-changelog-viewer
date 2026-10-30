# APT Changelog Viewer

View changelogs for installed Debian/Ubuntu packages. CVE and Debian/Ubuntu security-advisory references are highlighted so they are easier to find; a reference alone does not prove that a security fix is available or installed.

Search the installed package list by package name or package description.

Selecting a package reads up to 50,000 characters of its local changelog. Use **Fetch online changelog** to request a remote copy. The app asks before contacting the APT-configured changelog server and explains that it can see your IP address and the package name. The request uses APT's configured source; Apt Changelog Viewer does not install packages or upload a report.

Built with GTK4/Adwaita. Part of the [Danne L10n Suite](https://github.com/yeager/debian-repo).

## Installation

## Installation from PyPI

GTK4, libadwaita and PyGObject must be installed from your distribution (they
are native system libraries and are not installed by pip). On Debian/Ubuntu:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 pipx
pipx install --system-site-packages apt-changelog-viewer
```



### Debian/Ubuntu
```bash
sudo apt install apt-changelog-viewer
```

## License

GPL-3.0

## Author

Daniel Nylander — [danielnylander.se](https://danielnylander.se)
