"""Command line entrypoint. This module declares the Copier CLI applications.

Basically, there are 3 different commands you can run:

-   [`copier`][copier.cli.CopierApp], the main app, which is a shortcut for the
    `copy` and `update` subapps.

    If the destination project is found and has [an answers
    file][the-copier-answersyml-file] with enough information, it will become a
    shortcut for `copier update`.

    Otherwise it will be a shortcut for `copier copy`.

    !!! example

        ```sh
        # Copy a new project
        copier gh:copier-org/autopretty my-project
        # Update it
        cd my-project
        copier
        ```

-   [`copier copy`][copier.cli.CopierApp], used to bootstrap a new project from
    a template.

    !!! example

        ```sh
        copier copy gh:copier-org/autopretty my-project
        ```

-   [`copier update`][copier.cli.CopierUpdateSubApp] to update a preexisting
    project to a newer version of its template.

    !!! example

        ```sh
        copier update
        ```

Below are the docs of each one of those.

CLI help generated from `copier --help-all`:

```sh exec="on" result="text"
copier --help-all
```
"""

import sys
from os import PathLike
from pathlib import Path
from textwrap import dedent
from typing import Callable

import yaml
from plumbum import cli, colors

from .errors import UnsafeTemplateError, UserMessageError
from .main import Worker
from .tools import copier_version
from .types import AnyByStrDict, OptStr, StrSeq


def _handle_exceptions(method: Callable[[], None]) -> int:
    """Handle keyboard interruption while running a method."""
    try:
        try:
            method()
        except KeyboardInterrupt as e:
            raise UserMessageError("Execution stopped by user") from e
    except UserMessageError as error:
        print(colors.red | "\n".join(error.args), file=sys.stderr)
        return 1
    except UnsafeTemplateError as error:
        print(colors.red | "\n".join(error.args), file=sys.stderr)
        # DOCS https://github.com/copier-org/copier/issues/1328#issuecomment-1723214165
        return 0b100
    return 0


class CopierApp(cli.Application):
    """The Copier CLI application."""

    DESCRIPTION = "Create a new project from a template."
    DESCRIPTION_MORE = dedent(
        """\
            Docs in https://copier.readthedocs.io/

            """
    ) + (
        colors.yellow
        | dedent(
            """\
                WARNING! Use only trusted project templates, as they might
                execute code with the same level of access as your user.\n
                """
        )
    )
    VERSION = copier_version()
    CALL_MAIN_IF_NESTED_COMMAND = False


class _Subcommand(cli.Application):
    """Base class for Copier subcommands."""

    def __init__(self, executable: PathLike) -> None:
        self.data: AnyByStrDict = {}
        super().__init__(executable)

    answers_file = cli.SwitchAttr(
        ["-a", "--answers-file"],
        default=None,
        help=(
            "Update using this path (relative to `destination_path`) "
            "to find the answers file"
        ),
    )
    exclude = cli.SwitchAttr(
        ["-x", "--exclude"],
        str,
        list=True,
        help=(
            "A name or shell-style pattern matching files or folders "
            "that must not be copied"
        ),
    )
    vcs_ref = cli.SwitchAttr(
        ["-r", "--vcs-ref"],
        str,
        help=(
            "Git reference to checkout in `template_src`. "
            "If you do not specify it, it will try to checkout the latest git tag, "
            "as sorted using the PEP 440 algorithm. If you want to checkout always "
            "the latest version, use `--vcs-ref=HEAD`."
        ),
    )
    pretend = cli.Flag(["-n", "--pretend"], help="Run but do not make any changes")
    skip = cli.SwitchAttr(
        ["-s", "--skip"],
        str,
        list=True,
        help="Skip specified files if they exist already",
    )
    quiet = cli.Flag(["-q", "--quiet"], help="Suppress status output")
    prereleases = cli.Flag(
        ["-g", "--prereleases"],
        help="Use prereleases to compare template VCS tags.",
    )
    unsafe = cli.Flag(
        ["--UNSAFE", "--trust"],
        help=(
            "Allow templates with unsafe features (Jinja extensions, migrations, tasks)"
        ),
    )

    @cli.switch(
        ["-d", "--data"],
        str,
        "VARIABLE=VALUE",
        list=True,
        help="Make VARIABLE available as VALUE when rendering the template",
    )
    def data_switch(self, values: StrSeq) -> None:
        """Update [data][] with provided values.

        Arguments:
            values: The list of values to apply.
                Each value in the list is of the following form: `NAME=VALUE`.
        """
        for arg in values:
            key, value = arg.split("=", 1)
            self.data[key] = value

    @cli.switch(
        ["--data-file"],
        cli.ExistingFile,
        help="Load data from a YAML file",
    )
    def data_file_switch(self, path: cli.ExistingFile) -> None:
        """Update [data][] with provided values.

        Arguments:
            path: The path to the YAML file to load.
        """
        with open(path) as f:
            file_updates: AnyByStrDict = yaml.safe_load(f)

        updates_without_cli_overrides = {
            k: v for k, v in file_updates.items() if k not in self.data
        }
        self.data.update(updates_without_cli_overrides)

    def _worker(self, src_path: OptStr = None, dst_path: str = ".", **kwargs) -> Worker:
        """Run Copier's internal API using CLI switches.

        Arguments:
            src_path: The source path of the template to generate the project from.
            dst_path: The path to generate the project to.
            **kwargs: Arguments passed to [Worker][copier.main.Worker].
        """
        return Worker(
            data=self.data,
            dst_path=Path(dst_path),
            answers_file=self.answers_file,
            exclude=self.exclude,
            pretend=self.pretend,
            skip_if_exists=self.skip,
            quiet=self.quiet,
            src_path=src_path,
            vcs_ref=self.vcs_ref,
            use_prereleases=self.prereleases,
            unsafe=self.unsafe,
            **kwargs,
        )


@CopierApp.subcommand("copy")
class CopierCopySubApp(_Subcommand):
    """The `copier copy` subcommand.

    Use this subcommand to bootstrap a new subproject from a template, or to override
    a preexisting subproject ignoring its history diff.
    """

    DESCRIPTION = "Copy from a template source to a destination."

    cleanup_on_error = cli.Flag(
        ["-C", "--no-cleanup"],
        default=True,
        help="On error, do not delete destination if it was created by Copier.",
    )
    defaults = cli.Flag(
        ["-l", "--defaults"],
        help="Use default answers to questions, which might be null if not specified.",
    )
    force = cli.Flag(
        ["-f", "--force"],
        help="Same as `--defaults --overwrite`.",
    )
    overwrite = cli.Flag(
        ["-w", "--overwrite"],
        help="Overwrite files that already exist, without asking.",
    )

    def main(self, template_src: str, destination_path: str) -> int:
        """Call [run_copy][copier.main.Worker.run_copy].

        Params:
            template_src:
                Indicate where to get the template from.

                This can be a git URL or a local path.

            destination_path:
                Where to generate the new subproject. It must not exist or be empty.
        """

        def inner() -> None:
            with self._worker(
                template_src,
                destination_path,
                cleanup_on_error=self.cleanup_on_error,
                defaults=self.force or self.defaults,
                overwrite=self.force or self.overwrite,
            ) as worker:
                worker.run_copy()

        return _handle_exceptions(inner)


@CopierApp.subcommand("recopy")
class CopierRecopySubApp(_Subcommand):
    """The `copier recopy` subcommand.

    Use this subcommand to update an existing subproject from a template that
    supports updates, ignoring any subproject evolution since the last Copier
    execution.
    """

    DESCRIPTION = "Recopy a subproject from its original template"
    DESCRIPTION_MORE = dedent(
        """\
        The copy must have a valid answers file which contains info from the
        last Copier execution, including the source template (it must be a key
        called `_src_path`).

        This command will ignore any diff that you have generated since the
        last `copier` execution. It will act as if it were the 1st time you
        apply the template to the destination path. However, it will keep the
        answers.

        If you want a smarter update that respects your project evolution, use
        `copier update` instead.
        """
    )

    defaults = cli.Flag(
        ["-l", "--defaults"],
        help="Use default answers to questions, which might be null if not specified.",
    )
    force = cli.Flag(
        ["-f", "--force"],
        help="Same as `--defaults --overwrite`.",
    )
    overwrite = cli.Flag(
        ["-w", "--overwrite"],
        help="Overwrite files that already exist, without asking.",
    )
    skip_answered = cli.Flag(
        ["-A", "--skip-answered"],
        default=False,
        help="Skip questions that have already been answered",
    )

    def main(self, destination_path: cli.ExistingDirectory = ".") -> int:
        """Call [run_recopy][copier.main.Worker.run_recopy].

        Parameters:
            destination_path:
                Only the destination path is needed to update, because the
                `src_path` comes from [the answers file][the-copier-answersyml-file].

                The subproject must exist. If not specified, the currently
                working directory is used.
        """

        def inner() -> None:
            with self._worker(
                dst_path=destination_path,
                defaults=self.force or self.defaults,
                overwrite=self.force or self.overwrite,
                skip_answered=self.skip_answered,
            ) as worker:
                worker.run_recopy()

        return _handle_exceptions(inner)


@CopierApp.subcommand("update")
class CopierUpdateSubApp(_Subcommand):
    """The `copier update` subcommand.

    Use this subcommand to update an existing subproject from a template
    that supports updates, respecting that subproject evolution since the last
    Copier execution.
    """

    DESCRIPTION = "Update a subproject from its original template"
    DESCRIPTION_MORE = dedent(
        """\
        The copy must have a valid answers file which contains info
        from the last Copier execution, including the source template
        (it must be a key called `_src_path`).

        If that file contains also `_commit`, and `destination_path` is a git
        repository, this command will do its best to respect the diff that you have
        generated since the last `copier` execution. To avoid that, use `copier recopy`
        instead.
        """
    )

    conflict = cli.SwitchAttr(
        ["-o", "--conflict"],
        cli.Set("rej", "inline"),
        default="inline",
        help=(
            "Behavior on conflict: Create .rej files, or add inline conflict markers."
        ),
    )
    context_lines = cli.SwitchAttr(
        ["-c", "--context-lines"],
        int,
        default=3,
        help=(
            "Lines of context to use for detecting conflicts. Increase for "
            "accuracy, decrease for resilience."
        ),
    )
    defaults = cli.Flag(
        ["-l", "-f", "--defaults"],
        help="Use default answers to questions, which might be null if not specified.",
    )
    skip_answered = cli.Flag(
        ["-A", "--skip-answered"],
        default=False,
        help="Skip questions that have already been answered",
    )

    def main(self, destination_path: cli.ExistingDirectory = ".") -> int:
        """Call [run_update][copier.main.Worker.run_update].

        Parameters:
            destination_path:
                Only the destination path is needed to update, because the
                `src_path` comes from [the answers file][the-copier-answersyml-file].

                The subproject must exist. If not specified, the currently
                working directory is used.
        """

        def inner() -> None:
            with self._worker(
                dst_path=destination_path,
                conflict=self.conflict,
                context_lines=self.context_lines,
                defaults=self.defaults,
                skip_answered=self.skip_answered,
                overwrite=True,
            ) as worker:
                worker.run_update()

        return _handle_exceptions(inner)
