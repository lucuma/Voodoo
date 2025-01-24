"""Utilities related to VCS."""

from __future__ import annotations

import os
import re
import sys
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from warnings import warn

from packaging import version
from packaging.version import InvalidVersion, Version
from plumbum import TF, ProcessExecutionError, colors, local
from plumbum.machines import LocalCommand

from .errors import DirtyLocalWarning, ShallowCloneWarning
from .types import OptBool, OptStrOrPath, StrOrPath

GIT_USER_NAME = "Copier"
GIT_USER_EMAIL = "copier@copier"


def get_git(context_dir: OptStrOrPath = None) -> LocalCommand:
    """Gets `git` command, or fails if it's not available."""
    command = local["git"].with_env(
        GIT_AUTHOR_NAME=GIT_USER_NAME,
        GIT_AUTHOR_EMAIL=GIT_USER_EMAIL,
        GIT_COMMITTER_NAME=GIT_USER_NAME,
        GIT_COMMITTER_EMAIL=GIT_USER_EMAIL,
    )
    if context_dir:
        command = command["-C", context_dir]
    return command


def get_git_version() -> Version:
    """Get the installed git version."""
    git = get_git()

    return Version(re.findall(r"\d+\.\d+\.\d+", git("version"))[0])


GIT_PREFIX = ("git@", "git://", "git+", "https://github.com/", "https://gitlab.com/")
GIT_POSTFIX = ".git"


def is_git_repo_root(path: StrOrPath) -> bool:
    """Indicate if a given path is a git repo root directory."""
    try:
        with local.cwd(Path(path, ".git")):
            return get_git()("rev-parse", "--is-inside-git-dir").strip() == "true"
    except OSError:
        return False


def is_in_git_repo(path: StrOrPath) -> bool:
    """Indicate if a given path is in a git repo directory."""
    try:
        get_git()("-C", path, "rev-parse", "--show-toplevel")
        return True
    except (OSError, ProcessExecutionError):
        return False


def is_git_shallow_repo(path: StrOrPath) -> bool:
    """Indicate if a given path is a git shallow repo directory."""
    try:
        return (
            get_git()("-C", path, "rev-parse", "--is-shallow-repository").strip()
            == "true"
        )
    except (OSError, ProcessExecutionError):
        return False


def is_git_bundle(path: Path) -> bool:
    """Indicate if a path is a valid git bundle."""
    with suppress(OSError):
        path = path.resolve()
    with TemporaryDirectory(prefix=f"{__name__}.is_git_bundle.") as dirname:
        with local.cwd(dirname):
            get_git()("init")
            return bool(get_git()["bundle", "verify", path] & TF)


def get_repo(url: str) -> str | None:
    """Transform `url` into a git-parseable origin URL.

    Args:
        url:
            Valid examples:

            - git@github.com:copier-org/copier.git
            - git+https://mywebsiteisagitrepo.example.com/
            - /local/path/to/git/repo
            - /local/path/to/git/bundle/file.bundle
            - ~/path/to/git/repo
            - ~/path/to/git/repo.bundle
    """
    if url.endswith(GIT_POSTFIX) or url.startswith(GIT_PREFIX):
        if url.startswith("git+"):
            return url[4:]
        if url.startswith("https://") and not url.endswith(GIT_POSTFIX):
            return "".join((url, GIT_POSTFIX))
        return url

    url_path = Path(url)
    if url.startswith("~"):
        url_path = url_path.expanduser()

    if is_git_repo_root(url_path) or is_git_bundle(url_path):
        return url_path.as_posix()

    return None


def checkout_latest_tag(local_repo: StrOrPath, use_prereleases: OptBool = False) -> str:
    """Checkout latest git tag and check it out, sorted by PEP 440.

    Parameters:
        local_repo:
            A git repository in the local filesystem.
        use_prereleases:
            If `False`, skip prerelease git tags.
    """
    git = get_git()
    with local.cwd(local_repo):
        all_tags = filter(valid_version, git("tag").split())
        if not use_prereleases:
            all_tags = filter(
                lambda tag: not version.parse(tag).is_prerelease, all_tags
            )
        sorted_tags = sorted(all_tags, key=version.parse, reverse=True)
        try:
            latest_tag = str(sorted_tags[0])
        except IndexError:
            print(
                colors.warn | "No git tags found in template; using HEAD as ref",
                file=sys.stderr,
            )
            latest_tag = "HEAD"
        git("checkout", "--force", latest_tag)
        git("submodule", "update", "--checkout", "--init", "--recursive", "--force")
        return latest_tag


def clone(url: str, ref: str | None = None) -> str:
    """Clone repo into some temporary destination.

    Includes dirty changes for local templates by copying into a temp
    directory and applying a wip commit there.

    Args:
        url:
            Git-parseable URL of the repo. As returned by
            [get_repo][copier.vcs.get_repo].
        ref:
            Reference to checkout. For Git repos, defaults to `HEAD`.
    """
    git = get_git()
    git_version = get_git_version()
    location = mkdtemp(prefix=f"{__name__}.clone.")
    _clone = git["clone", "--no-checkout", url, location]
    # Faster clones if possible
    if git_version >= Version("2.27"):
        if url_match := re.match("(file://)?(.*)", url):
            file_url = url_match.groups()[-1]
        else:
            file_url = url
        if is_git_shallow_repo(file_url):
            warn(
                f"The repository '{url}' is a shallow clone, this might lead to unexpected "
                "failure or unusually high resource consumption.",
                ShallowCloneWarning,
            )
        else:
            _clone = _clone["--filter=blob:none"]
    _clone()
    # Include dirty changes if checking out a local HEAD
    if ref in {None, "HEAD"} and os.path.exists(url) and Path(url).is_dir():
        is_dirty = False
        with local.cwd(url):
            is_dirty = bool(git("status", "--porcelain").strip())
        if is_dirty:
            url_abspath = Path(url).absolute()
            with local.cwd(location):
                git("--git-dir=.git", f"--work-tree={url_abspath}", "add", "-A")
                git(
                    "--git-dir=.git",
                    f"--work-tree={url_abspath}",
                    "commit",
                    "-m",
                    "Copier automated commit for draft changes",
                    "--no-verify",
                    "--no-gpg-sign",
                )
                warn(
                    "Dirty template changes included automatically.",
                    DirtyLocalWarning,
                )

    with local.cwd(location):
        git("checkout", "-f", ref or "HEAD")
        git("submodule", "update", "--checkout", "--init", "--recursive", "--force")

    return location


def valid_version(version_: str) -> bool:
    """Tell if a string is a valid [PEP 440][] version specifier.

    [PEP 440]: https://peps.python.org/pep-0440/
    """
    try:
        version.parse(version_)
    except InvalidVersion:
        return False
    return True
