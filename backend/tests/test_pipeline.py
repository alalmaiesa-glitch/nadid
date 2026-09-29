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


def test_parser_node_ids_are_stable_for_same_docx():
    from io import BytesIO
    from docx import Document
    from app.pipeline.parser import parse_docx

    document = Document()
    document.add_heading("مقدمة", level=1)
    document.add_paragraph("هذا نص تجريبي ثابت.")
    stream = BytesIO()
    document.save(stream)
    payload = stream.getvalue()

    first = parse_docx(payload)
    second = parse_docx(payload)

    assert [item.id for item in first] == [item.id for item in second]


def test_chunk_ids_are_stable():
    nodes = [
        node("الفقرة الأولى في المستند.", 0),
        node("الفقرة الثانية في المستند.", 1),
    ]

    first = build_chunks(nodes, target_tokens=100)
    second = build_chunks(nodes, target_tokens=100)

    assert [item.id for item in first] == [item.id for item in second]


def test_fact_ids_are_stable():
    from app.pipeline.facts import extract_facts

    nodes = [node("تبلغ الطاقة الإنتاجية 2000000 وحدة سنويًا.", 0)]

    first = extract_facts(nodes)
    second = extract_facts(nodes)

    assert [item.id for item in first] == [item.id for item in second]


def test_arabic_numeric_forms_are_canonicalized():
    from app.arabic_numbers import canonical_decimal

    assert canonical_decimal("٣٨٬٧٧١٬٢٥١ ريال") == "38771251"
    assert canonical_decimal("١٨٫٦٪") == "18.6"


def test_protection_extracts_arabic_currency_percentage_and_year():
    from app.pipeline.protection import extract_protected_spans

    spans = extract_protected_spans([
        node("بلغت التكلفة ٣٨٬٧٧١٬٢٥١ ريال في عام ٢٠٢٦ بنسبة ١٨٫٦٪.", 0)
    ])

    values = {(span.type, span.value) for span in spans}

    assert ("currency", "٣٨٬٧٧١٬٢٥١ ريال") in values
    assert ("date", "٢٠٢٦") in values
    assert ("percentage", "١٨٫٦٪") in values


def test_fact_lock_allows_equivalent_numeric_format():
    text = "بلغت التكلفة ٣٨٬٧٧١٬٢٥١ ريال."
    protected = [
        ProtectedSpan(
            id="arabic-number",
            node_id="n-0",
            type="currency",
            value="٣٨٬٧٧١٬٢٥١ ريال",
            validator_key="numeric_equivalence",
        )
    ]

    result = validate_patch(
        block_text=text,
        original="٣٨٬٧٧١٬٢٥١ ريال",
        replacement="38,771,251 ريال",
        protected_spans=protected,
    )

    assert result.status == "PASS"


def test_fact_lock_blocks_changed_arabic_number():
    text = "بلغت التكلفة ٣٨٬٧٧١٬٢٥١ ريال."
    protected = [
        ProtectedSpan(
            id="arabic-number",
            node_id="n-0",
            type="currency",
            value="٣٨٬٧٧١٬٢٥١ ريال",
            validator_key="numeric_equivalence",
        )
    ]

    result = validate_patch(
        block_text=text,
        original="٣٨٬٧٧١٬٢٥١",
        replacement="٣٩٬٧٧١٬٢٥١",
        protected_spans=protected,
    )

    assert result.status == "BLOCK"


def test_docx_patch_preserves_surrounding_run_formatting():
    from io import BytesIO
    from docx import Document
    from app.pipeline.docx_patch import apply_patches_to_docx
    from app.pipeline.parser import parse_docx
    from app.contracts import PatchOperation

    document = Document()
    paragraph = document.add_paragraph()
    first = paragraph.add_run("بلغت التكلفة ")
    first.bold = True
    paragraph.add_run("38,771,251 ريال ، وهي معتمدة.")

    source = BytesIO()
    document.save(source)
    payload = source.getvalue()

    nodes = parse_docx(payload)
    target = nodes[0]

    output, report = apply_patches_to_docx(
        payload,
        [
            PatchOperation(
                node_id=target.id,
                original="ريال ،",
                replacement="ريال،",
            )
        ],
    )

    assert len(report.applied) == 1
    assert not report.skipped

    result = Document(BytesIO(output))
    result_paragraph = result.paragraphs[0]

    assert "38,771,251 ريال، وهي معتمدة." in result_paragraph.text
    assert result_paragraph.runs[0].bold is True


def test_parser_node_identity_survives_text_edit():
    from io import BytesIO
    from docx import Document
    from app.pipeline.parser import parse_docx

    first_document = Document()
    first_document.add_paragraph("النص قبل التصحيح.")
    first_stream = BytesIO()
    first_document.save(first_stream)

    second_document = Document()
    second_document.add_paragraph("النص بعد التصحيح.")
    second_stream = BytesIO()
    second_document.save(second_stream)

    first_nodes = parse_docx(first_stream.getvalue())
    second_nodes = parse_docx(second_stream.getvalue())

    assert first_nodes[0].id == second_nodes[0].id

def test_meaning_lock_extracts_entity_and_legal_reference():
    from app.pipeline.protection import extract_protected_spans

    spans = extract_protected_spans([
        node("تتولى وزارة الحج والعمرة الإشراف وفق المادة (12).", 0)
    ])
    values = {(span.type, span.value) for span in spans}

    assert ("entity", "وزارة الحج والعمرة") in values
    assert ("legal_reference", "المادة (12)") in values


def test_meaning_lock_blocks_entity_change():
    from app.pipeline.protection import extract_protected_spans

    text = "تتولى وزارة الحج والعمرة الإشراف على البرنامج."
    spans = extract_protected_spans([node(text, 0)])

    result = validate_patch(
        block_text=text,
        original="وزارة الحج والعمرة",
        replacement="وزارة السياحة",
        protected_spans=spans,
    )

    assert result.status == "BLOCK"


def test_meaning_lock_blocks_currency_unit_change():
    from app.pipeline.protection import extract_protected_spans

    text = "تبلغ القيمة 100 ريال."
    spans = extract_protected_spans([node(text, 0)])

    result = validate_patch(
        block_text=text,
        original="100 ريال",
        replacement="100 دولار",
        protected_spans=spans,
    )

    assert result.status == "BLOCK"


def test_meaning_lock_allows_equivalent_numeric_format_with_unit():
    from app.pipeline.protection import extract_protected_spans

    text = "تبلغ القيمة ٣٨٬٧٧١٬٢٥١ ريال."
    spans = extract_protected_spans([node(text, 0)])

    result = validate_patch(
        block_text=text,
        original="٣٨٬٧٧١٬٢٥١ ريال",
        replacement="38,771,251 ريال",
        protected_spans=spans,
    )

    assert result.status == "PASS"


def test_meaning_lock_blocks_obligation_relaxation():
    from app.pipeline.protection import extract_protected_spans

    text = "يجب على المورد تسليم المواد خلال خمسة أيام."
    spans = extract_protected_spans([node(text, 0)])

    result = validate_patch(
        block_text=text,
        original="يجب على",
        replacement="يمكن لـ",
        protected_spans=spans,
    )

    assert result.status == "BLOCK"


def test_meaning_lock_blocks_condition_removal():
    from app.pipeline.protection import extract_protected_spans

    text = "إذا تأخر المورد، يطبق الإجراء التصحيحي."
    spans = extract_protected_spans([node(text, 0)])

    result = validate_patch(
        block_text=text,
        original="إذا ",
        replacement="",
        protected_spans=spans,
    )

    assert result.status == "BLOCK"


def test_meaning_lock_allows_punctuation_normalization_in_critical_clause():
    from app.pipeline.protection import extract_protected_spans

    text = "لا يتحمل الطرف الأول تكاليف النقل ، وفق العقد."
    spans = extract_protected_spans([node(text, 0)])

    result = validate_patch(
        block_text=text,
        original="النقل ،",
        replacement="النقل،",
        protected_spans=spans,
    )

    assert result.status == "PASS"


def test_meaning_lock_blocks_introduced_negation():
    from app.pipeline.protection import extract_protected_spans

    text = "المشروع مكتمل وفق المحضر النهائي."
    spans = extract_protected_spans([node(text, 0)])

    result = validate_patch(
        block_text=text,
        original="مكتمل",
        replacement="غير مكتمل",
        protected_spans=spans,
    )

    assert result.status == "BLOCK"

def test_meaning_lock_blocks_full_date_reordering():
    from app.pipeline.protection import extract_protected_spans

    text = "موعد التسليم هو 15/10/2026."
    spans = extract_protected_spans([node(text, 0)])
    result = validate_patch(
        block_text=text,
        original="15/10/2026",
        replacement="10/15/2026",
        protected_spans=spans,
    )
    assert result.status == "BLOCK"


def test_meaning_lock_blocks_quantity_unit_change():
    from app.pipeline.protection import extract_protected_spans

    text = "المسافة المعتمدة 100 متر."
    spans = extract_protected_spans([node(text, 0)])
    result = validate_patch(
        block_text=text,
        original="100 متر",
        replacement="100 كيلومتر",
        protected_spans=spans,
    )
    assert result.status == "BLOCK"


def test_meaning_lock_blocks_added_uncertainty():
    from app.pipeline.protection import extract_protected_spans

    text = "المشروع مكتمل وفق المحضر."
    spans = extract_protected_spans([node(text, 0)])
    result = validate_patch(
        block_text=text,
        original="مكتمل",
        replacement="قد يكون مكتمل",
        protected_spans=spans,
    )
    assert result.status == "BLOCK"


def test_meaning_lock_blocks_logic_operator_change():
    from app.pipeline.protection import extract_protected_spans

    text = "يشمل النطاق النقل أو التخزين."
    spans = extract_protected_spans([node(text, 0)])
    result = validate_patch(
        block_text=text,
        original="أو",
        replacement="و",
        protected_spans=spans,
    )
    assert result.status == "BLOCK"

def test_document_memory_extracts_definition_and_abbreviation():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        node("يقصد بمصطلح «مقدم الخدمة»: الجهة المتعاقدة لتنفيذ الأعمال.", 0),
        node("الهيئة العامة للعقار (REGA) تشرف على تنظيم القطاع.", 1),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    assert any(
        item.kind == "definition"
        and "مقدم الخدمة" in item.key
        and "الجهة المتعاقدة" in item.value
        for item in memory.knowledge_items
    )
    assert any(
        item.kind == "abbreviation"
        and item.key == "REGA"
        and "الهيئة العامة للعقار" in item.value
        for item in memory.knowledge_items
    )


def test_document_memory_aggregates_entity_mentions():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        node("تعمل وزارة الصحة على تطوير الخدمة.", 0),
        node("تتولى وزارة الصحة الإشراف على التنفيذ.", 1),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    item = next(
        item
        for item in memory.knowledge_items
        if item.kind == "entity" and item.key == "وزارة الصحة"
    )
    assert set(item.node_ids) == {"n-0", "n-1"}


def test_document_memory_extracts_decisions_obligations_and_conditions():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        node("تم اعتماد الخطة التشغيلية في الاجتماع الأخير.", 0),
        node("يجب على المورد تسليم التقرير خلال خمسة أيام.", 1),
        node("إذا تأخر المورد، يطبق الإجراء التصحيحي.", 2),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    kinds = {item.kind for item in memory.knowledge_items}
    assert "decision" in kinds
    assert "obligation" in kinds
    assert "condition" in kinds


def test_document_memory_promotes_repeated_multiword_concept():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        node("يعتمد المشروع على الذكاء الاصطناعي في التحليل.", 0),
        node("يساعد الذكاء الاصطناعي في تحسين جودة المراجعة.", 1),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    assert any(
        item.kind == "concept"
        and "الذكاء الاصطناعي" in item.key
        and len(item.node_ids) == 2
        for item in memory.knowledge_items
    )


def test_document_memory_does_not_treat_heading_colon_as_definition():
    from app.contracts import DocumentNode
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        DocumentNode(
            id="h-1",
            type="heading",
            text="مقدمة: خلفية المشروع",
            sequence_no=0,
        )
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    assert not any(
        item.kind == "definition" and "مقدمة" in item.key
        for item in memory.knowledge_items
    )

def test_document_memory_extracts_explicit_relation():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        node("وزارة الحج والعمرة تشرف على برنامج خدمة ضيوف الرحمن.", 0)
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    relation = next(
        item
        for item in memory.knowledge_items
        if item.kind == "relation"
    )
    assert relation.key == "وزارة الحج والعمرة"
    assert "برنامج خدمة ضيوف الرحمن" in relation.value
    assert relation.metadata["predicate"] == "تشرف على"

