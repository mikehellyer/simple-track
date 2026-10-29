import sys
from pathlib import Path

from simple_track import __version__


def self_test() -> int:
    """`Simple-Track --self-test`: checks a built app has everything it
    needs bundled (the release workflow runs this on each OS). Exit code
    0 if so."""
    checks = {}
    try:
        from simple_track.core.library import builtin_libraries

        libraries = builtin_libraries()
        checks["track libraries"] = len(libraries) >= 7 and all(lib.pieces for lib in libraries)
    except Exception:
        checks["track libraries"] = False
    try:
        from simple_track.core.layout import Layout

        layout = Layout()
        first = layout.place("peco-oo-setrack", "ST-200")
        layout.place("peco-oo-setrack", "ST-225", first.connectors()[1])
        checks["layout"] = len(layout.free_connectors()) == 2
    except Exception:
        checks["layout"] = False
    try:
        from simple_track.core import anyrail  # noqa: F401

        checks["AnyRail import"] = True
    except Exception:
        checks["AnyRail import"] = False
    try:
        import certifi  # noqa: F401

        checks["certificates"] = True
    except Exception:
        checks["certificates"] = False
    report = ", ".join(f"{name}: {'ok' if ok else 'MISSING'}" for name, ok in checks.items())
    try:
        print(f"Simple-Track {__version__} self-test — {report}", flush=True)
    except (AttributeError, OSError):  # no console (Windows GUI build)
        pass
    return 0 if all(checks.values()) else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    # Qt is imported only now, so --self-test runs even where there's no
    # display or graphics libraries (the release workflow's build machines).
    from PySide6.QtWidgets import QApplication

    from simple_track.core.diagnostics import enable_app_log, enable_crash_log, log_event
    from simple_track.gui.main_window import MainWindow

    enable_app_log(__version__)
    enable_crash_log()
    app = QApplication(sys.argv)
    app.setApplicationName("Simple-Track")
    app.setDesktopFileName("simple-track")
    window = MainWindow()
    window.show()
    # A layout passed on the command line (or by double-clicking a file) opens straight away.
    files = [Path(arg) for arg in sys.argv[1:] if not arg.startswith("-") and Path(arg).is_file()]
    if files:
        window.open_path(files[0])
    code = app.exec()
    log_event(f"event loop finished (code {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())
