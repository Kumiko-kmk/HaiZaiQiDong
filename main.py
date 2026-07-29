"""Entry point for mouse sketch drawer."""

from core.elevation import ElevationError, ensure_administrator, show_elevation_error


def main() -> int:
    try:
        if not ensure_administrator():
            return 0
    except ElevationError as exc:
        show_elevation_error(str(exc))
        return 1

    from core.runtime_logging import configure_runtime_logging
    from gui.pythonnet_runtime import configure_frozen_pythonnet
    from gui.tk_env import ensure_tcl_tk_env

    configure_runtime_logging()
    configure_frozen_pythonnet()
    ensure_tcl_tk_env()

    from gui.webview_app import run_app

    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
