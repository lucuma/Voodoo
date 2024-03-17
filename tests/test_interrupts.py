from unittest.mock import Mock, patch

import pytest

from copier import Worker
from copier.errors import CopierAnswersInterrupt

from .helpers import build_file_tree


@pytest.mark.parametrize(
    "side_effect",
    [
        # We override the prompt method from questionary to raise this
        # exception and expect our surrounding machinery to re-raise
        # it as a CopierAnswersInterrupt.
        CopierAnswersInterrupt(Mock(), Mock(), Mock()),
        KeyboardInterrupt,
    ],
)
def test_keyboard_interrupt(
    tmp_path_factory: pytest.TempPathFactory, side_effect: KeyboardInterrupt
) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (src / "copier.yml"): (
            """\
                question:
                    type: str
                """
        ),
    })
    worker = Worker(str(src), dst, defaults=False)

    with patch("copier.main.unsafe_prompt", side_effect=side_effect):
        with pytest.raises(KeyboardInterrupt):
            worker.run_copy()


def test_multiple_questions_interrupt(tmp_path_factory: pytest.TempPathFactory) -> None:
    src, dst = map(tmp_path_factory.mktemp, ("src", "dst"))
    build_file_tree({
        (src / "copier.yml"): (
            """\
                question1:
                    type: str
                question2:
                    type: str
                question3:
                    type: str
                """
        ),
    })
    worker = Worker(str(src), dst, defaults=False)

    with patch(
        "copier.main.unsafe_prompt",
        side_effect=[
            {"question1": "foobar"},
            {"question2": "yosemite"},
            KeyboardInterrupt,
        ],
    ):
        with pytest.raises(CopierAnswersInterrupt) as err:
            worker.run_copy()
        assert err.value.answers.user == {
            "question1": "foobar",
            "question2": "yosemite",
        }
        assert err.value.template == worker.template
