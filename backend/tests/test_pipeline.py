from app.contracts import DocumentNode, ProtectedSpan
from app.pipeline.chunker import build_chunks
from app.pipeline.patch_validator import validate_patch
from app.pipeline.reviewer import fast_review


def node(text: str, sequence: int = 0) -> DocumentNode:
    return DocumentNode(
        id=f"n-{sequence}",
        type="paragraph",
        text=text,
        sequence_no=sequence,
    )


def test_fast_review_detects_extra_preposition():
    issues = fast_review([node("يساهم ذلك في تحسين من مستوى الأداء.")])
    assert any(issue.replacement == "تحسين مستوى" for issue in issues)


def test_chunker_preserves_nodes():
    nodes = [
        node("فقرة قصيرة.", 0),
        node("فقرة أخرى.", 1),
    ]
    chunks = build_chunks(nodes, target_tokens=100)
    assert len(chunks) == 1
    assert chunks[0].node_ids == ["n-0", "n-1"]


def test_fact_lock_blocks_number_change():
    text = "بلغت التكلفة 38,771,251 ريال."
    protected = [
        ProtectedSpan(
            id="p1",
            node_id="n-0",
            type="currency",
            value="38,771,251 ريال",
            validator_key="numeric_equivalence",
        )
    ]

    result = validate_patch(
        block_text=text,
        original="38,771,251",
        replacement="39,771,251",
        protected_spans=protected,
    )

    assert result.status == "BLOCK"
    assert result.candidate == text


def test_fact_lock_allows_safe_style_edit():
    text = "بلغت التكلفة 38,771,251 ريال ، وهي معتمدة."
    protected = [
        ProtectedSpan(
            id="p1",
            node_id="n-0",
            type="currency",
            value="38,771,251 ريال",
            validator_key="numeric_equivalence",
        )
    ]

    result = validate_patch(
        block_text=text,
        original="ريال ،",
        replacement="ريال،",
        protected_spans=protected,
    )

    assert result.status == "PASS"
    assert "38,771,251 ريال" in result.candidate


def test_fact_lock_blocks_negation_removal():
    text = "ولا يسمح النظام بتغيير القيمة."
    protected = [
        ProtectedSpan(
            id="p2",
            node_id="n-0",
            type="negation",
            value="ولا يسمح النظام بتغيير القيمة",
            validator_key="negation_preservation",
            lock_policy="semantic_exact",
        )
    ]

    result = validate_patch(
        block_text=text,
        original="ولا يسمح",
        replacement="ويسمح",
        protected_spans=protected,
    )

    assert result.status == "BLOCK"
