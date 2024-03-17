import pytest

import copier

from .helpers import build_file_tree


def test_empty_suffix(tmp_path_factory: pytest.TempPathFactory) -> None:
    root, dest = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (root / "copier.yaml"): (
            """\
                _templates_suffix: ""
                name:
                    type: str
                    default: pingu
                """
        ),
        (root / "render_me"): "Hello {{name}}!",
        (root / "{{name}}.txt"): "Hello {{name}}!",
        (root / "{{name}}" / "render_me.txt"): "Hello {{name}}!",
    })
    copier.run_copy(str(root), dest, defaults=True, overwrite=True)

    assert not (dest / "copier.yaml").exists()

    assert (dest / "render_me").exists()
    assert (dest / "pingu.txt").exists()
    assert (dest / "pingu" / "render_me.txt").exists()

    expected = "Hello pingu!"
    assert (dest / "render_me").read_text() == expected
    assert (dest / "pingu.txt").read_text() == expected
    assert (dest / "pingu" / "render_me.txt").read_text() == expected


def test_binary_file_fallback_to_copy(tmp_path_factory: pytest.TempPathFactory) -> None:
    root, dest = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (root / "copier.yaml"): (
            """\
                _templates_suffix: ""
                name:
                    type: str
                    default: pingu
                """
        ),
        (root / "logo.png"): (
            b"\x89PNG\r\n\x1a\n\x00\rIHDR\x00\xec\n{{name}}\n\x00\xec"
        ),
    })
    copier.run_copy(str(root), dest, defaults=True, overwrite=True)
    logo = dest / "logo.png"
    assert logo.exists()
    logo_bytes = logo.read_bytes()
    assert b"{{name}}" in logo_bytes
    assert b"pingu" not in logo_bytes
