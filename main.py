"""Entry point for mouse sketch drawer."""

from gui.pythonnet_runtime import configure_frozen_pythonnet
from gui.tk_env import ensure_tcl_tk_env

configure_frozen_pythonnet()
ensure_tcl_tk_env()

from gui.webview_app import run_app


def main() -> None:
    run_app()


if __name__ == "__main__":
    main()
