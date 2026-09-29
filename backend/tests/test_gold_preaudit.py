from app.contracts import DocumentNode
from app.pipeline.reviewer import fast_review


def node(text: str) -> DocumentNode:
    return DocumentNode(
        id="gold-preaudit-node",
        type="paragraph",
        text=text,
        sequence_no=0,
    )


def test_number_unit_colon_is_replaced_not_re_spaced():
    issues = fast_review([node("المدة: 8 :أشهر.")])

    assert any(
        issue.title == "علامة ترقيم زائدة بين العدد والوحدة"
        and issue.replacement == "8 أشهر"
        for issue in issues
    )
    assert not any(
        issue.title in {
            "مسافة قبل علامة ترقيم",
            "مسافة بعد علامة ترقيم",
        }
        for issue in issues
    )


def test_period_spacing_is_completed_in_both_directions():
    issues = fast_review([
        node("الحل: سياج وحماية .الجفاف يعالج بخطة بديلة.")
    ])

    assert any(
        issue.title == "مسافة قبل علامة ترقيم"
        and issue.replacement == "."
        for issue in issues
    )
    assert any(
        issue.title == "مسافة بعد علامة ترقيم"
        and issue.replacement == ". "
        for issue in issues
    )
