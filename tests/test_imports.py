import pytest
import yaml

import copier
from copier.types import AnyByStrDict

from .helpers import build_file_tree


@pytest.mark.parametrize(
    "subdir, settings",
    [
        (
            "",
            {
                "_exclude": ["includes"],
            },
        ),
        (
            "template",
            {
                "_subdirectory": "template",
            },
        ),
    ],
)
def test_include(
    tmp_path_factory: pytest.TempPathFactory, subdir: str, settings: AnyByStrDict
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): yaml.safe_dump(
                {
                    **settings,
                    "name": {
                        "type": "str",
                        "default": "The Name",
                    },
                    "slug": {
                        "type": "str",
                        "default": "{% include 'includes/name-slug.jinja' %}",
                    },
                }
            ),
            (src / "includes" / "name-slug.jinja"): (
                "{{ name|lower|replace(' ', '-') }}"
            ),
            # File for testing the Jinja include statement in `copier.yml`.
            (src / subdir / "slug-answer.txt.jinja"): "{{ slug }}",
            # File for testing the Jinja include statement as content.
            (src / subdir / "slug-from-include.txt.jinja"): (
                "{% include 'includes/name-slug.jinja' %}"
            ),
            # File for testing the Jinja include statement in the file name.
            (
                src
                / subdir
                / "{% include pathjoin('includes', 'name-slug.jinja') %}.txt"
            ): "",
            # File for testing the Jinja include statement in the folder name.
            (
                src
                / subdir
                / "{% include pathjoin('includes', 'name-slug.jinja') %}"
                / "test.txt"
            ): "",
        }
    )
    copier.run_copy(str(src), dst, defaults=True)
    assert (dst / "slug-answer.txt").read_text() == "the-name"
    assert (dst / "slug-from-include.txt").read_text() == "the-name"
    assert (dst / "the-name.txt").exists()
    assert (dst / "the-name" / "test.txt").exists()
    assert not (dst / "includes").exists()


@pytest.mark.parametrize(
    "subdir, settings",
    [
        (
            "",
            {
                "_exclude": ["includes"],
            },
        ),
        (
            "template",
            {
                "_subdirectory": "template",
            },
        ),
    ],
)
def test_import_macro(
    tmp_path_factory: pytest.TempPathFactory, subdir: str, settings: AnyByStrDict
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree(
        {
            (src / "copier.yml"): yaml.safe_dump(
                {
                    **settings,
                    "name": {
                        "type": "str",
                        "default": "The Name",
                    },
                    "slug": {
                        "type": "str",
                        "default": (
                            "{% from 'includes/slugify.jinja' import slugify %}"
                            "{{ slugify(name) }}"
                        ),
                    },
                }
            ),
            (src / "includes" / "slugify.jinja"): (
                """\
                {% macro slugify(value) -%}
                {{ value|lower|replace(' ', '-') }}
                {%- endmacro %}
                """
            ),
            # File for testing the Jinja import statement in `copier.yml`.
            (src / subdir / "slug-answer.txt.jinja"): "{{ slug }}",
            # File for testing the Jinja import statement as content.
            (src / subdir / "slug-from-macro.txt.jinja"): (
                "{% from 'includes/slugify.jinja' import slugify %}"
                "{{ slugify(name) }}"
            ),
            # File for testing the Jinja import statement in the file name.
            (
                src
                / subdir
                / "{% from pathjoin('includes', 'slugify.jinja') import slugify %}{{ slugify(name) }}.txt"  # noqa: E501
            ): "",
            # File for testing the Jinja import statement in the folder name.
            (
                src
                / subdir
                / "{% from pathjoin('includes', 'slugify.jinja') import slugify %}{{ slugify(name) }}"  # noqa: E501
                / "test.txt"
            ): "",
        }
    )
    copier.run_copy(str(src), dst, defaults=True)
    assert (dst / "slug-answer.txt").read_text() == "the-name"
    assert (dst / "slug-from-macro.txt").read_text() == "the-name"
    assert (dst / "the-name.txt").exists()
    assert (dst / "the-name" / "test.txt").exists()
    assert not (dst / "includes").exists()
