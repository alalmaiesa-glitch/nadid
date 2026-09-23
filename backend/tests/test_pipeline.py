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


def test_document_memory_extracts_repeated_terms():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        node("يعتمد المشروع على الذكاء الاصطناعي في التحليل.", 0),
        node("يستخدم الذكاء الاصطناعي لتحسين المراجعة.", 1),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    assert any(term.term == "الذكاء" and term.count >= 2 for term in memory.terms)


def test_fact_conflict_detects_same_claim_different_value():
    from app.pipeline.facts import detect_fact_conflicts, extract_facts

    nodes = [
        node("عدد المحاور في النموذج 4 محاور.", 0),
        node("عدد المحاور في النموذج 5 محاور.", 1),
    ]
    facts = extract_facts(nodes)
    conflicts = detect_fact_conflicts(facts)

    assert len(conflicts) == 1
    assert set(conflicts[0].values) == {"4", "5"}


def test_context_retrieval_finds_related_chunk():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.context import retrieve_context
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        node("يعالج الفصل الأول الجوانب التشغيلية العامة.", 0),
        node("تبلغ الطاقة الإنتاجية للمصنع 2000000 وحدة سنويًا.", 1),
        node("يتناول هذا الجزء استراتيجية التسويق والتوزيع.", 2),
        node("تساعد الطاقة الإنتاجية في تقدير احتياجات المواد.", 3),
    ]
    chunks = build_chunks(nodes, target_tokens=7, hard_limit=15)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    package = retrieve_context(
        target_node_id="n-1",
        nodes=nodes,
        chunks=chunks,
        memory=memory,
        query="الطاقة الإنتاجية",
        max_chunks=3,
    )

    assert any("الطاقة الإنتاجية" in hit.text for hit in package.hits)
