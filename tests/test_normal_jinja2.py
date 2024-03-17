import warnings

import pytest

import copier

from .helpers import build_file_tree


def test_normal_jinja2(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (src / "copier.yml"): (
            """\
                _templates_suffix: .jinja
                _envops:
                    autoescape: false
                    variable_start_string: "{{"
                    variable_end_string: "}}"
                    block_start_string: "{%"
                    block_end_string: "%}"
                    comment_start_string: "{#"
                    comment_end_string: "#}"
                    lstrip_blocks: true
                    trim_blocks: true
                name: Guybrush
                todo: Become a pirate
                """
        ),
        (src / "TODO.txt.jinja"): (
            """\
                [[ {{ name }} TODO LIST]]
                {# Let's put an ugly not-comment below #}
                [# GROG #]
                    {% if name == 'Guybrush' %}
                    - {{ todo }}
                    {% endif %}
                """
        ),
    })
    # No warnings, because template is explicit
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        copier.run_copy(str(src), dst, defaults=True, overwrite=True)
    todo = (dst / "TODO.txt").read_text()
    expected = "[[ Guybrush TODO LIST]]\n[# GROG #]\n    - Become a pirate\n"
    assert todo == expected


def test_to_not_keep_trailing_newlines_in_jinja2(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (src / "copier.yml"): (
            """\
                _templates_suffix: .jinja
                _envops:
                    keep_trailing_newline: false
                data: foo
                """
        ),
        (src / "data.txt.jinja"): "This is {{ data }}.\n",
    })
    # No warnings, because template is explicit
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        copier.run_copy(str(src), dst, defaults=True, overwrite=True)
    assert (dst / "data.txt").read_text() == "This is foo."
