# APT Changelog Viewer

View changelogs for installed Debian/Ubuntu packages with security alert highlighting.

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
