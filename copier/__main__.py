"""Copier CLI entrypoint."""

from .cli import CopierApp

# HACK https://github.com/nix-community/poetry2nix/issues/504
copier_app_run = CopierApp.run
if __name__ == "__main__":
    copier_app_run()
