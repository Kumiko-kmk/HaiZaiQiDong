"""Entry point for mouse sketch drawer."""

from gui.tk_env import ensure_tcl_tk_env

ensure_tcl_tk_env()

from gui.webview_app import run_app


def main() -> None:
    run_app()


if __name__ == "__main__":
    main()
