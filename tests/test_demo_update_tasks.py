import pytest
from plumbum import local
from plumbum.cmd import git

from copier import run_copy, run_update

from .helpers import build_file_tree


def test_update_tasks(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Test that updating a template runs tasks from the expected version."""
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    # Prepare repo bundle
    repo = src / "repo"
    bundle = src / "demo_update_tasks.bundle"
    build_file_tree({
        (repo / ".copier-answers.yml.jinja"): (
            """\
                # Changes here will be overwritten by Copier
                {{ _copier_answers|to_nice_yaml }}
                """
        ),
        (repo / "copier.yaml"): (
            """\
                _tasks:
                    - cat v1.txt
                """
        ),
        (repo / "v1.txt"): "file only in v1",
    })
    with local.cwd(repo):
        git("init")
        git("add", ".")
        git("commit", "-m1")
        git("tag", "v1")
    build_file_tree({
        (repo / "copier.yaml"): (
            """\
                _tasks:
                    - cat v2.txt
                """
        ),
        (repo / "v2.txt"): "file only in v2",
    })
    (repo / "v1.txt").unlink()
    with local.cwd(repo):
        git("init")
        git("add", ".")
        git("commit", "-m2")
        git("tag", "v2")
        git("bundle", "create", bundle, "--all")
    # Copy the 1st version
    run_copy(str(bundle), dst, defaults=True, overwrite=True, vcs_ref="v1", unsafe=True)
    # Init destination as a new independent git repo
    with local.cwd(dst):
        git("init")
        # Configure git in case you're running in CI
        git("config", "user.name", "Copier Test")
        git("config", "user.email", "test@copier")
        # Commit changes
        git("add", ".")
        git("commit", "-m", "hello world")
    # Update target to v2
    run_update(dst_path=dst, defaults=True, overwrite=True, unsafe=True)
