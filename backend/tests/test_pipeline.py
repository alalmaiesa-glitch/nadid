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

def test_semantic_review_detects_definition_conflict():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans
    from app.pipeline.semantic_review import semantic_review

    nodes = [
        node("يقصد بمصطلح «مقدم الخدمة»: الجهة المتعاقدة لتنفيذ الأعمال.", 0),
        node("يقصد بمصطلح «مقدم الخدمة»: الجهة الحكومية المالكة للمشروع.", 1),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    issues = semantic_review(nodes, memory)

    assert any(
        issue.issue_type == "definition_conflict"
        for issue in issues
    )


def test_semantic_review_does_not_flag_equivalent_definition():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans
    from app.pipeline.semantic_review import semantic_review

    nodes = [
        node("يقصد بمصطلح «مقدم الخدمة»: الجهة المتعاقدة لتنفيذ الأعمال.", 0),
        node("يقصد بمصطلح «مقدم الخدمة»: الجهة المتعاقدة التي تنفذ الأعمال.", 1),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    issues = semantic_review(nodes, memory)

    assert not any(
        issue.issue_type == "definition_conflict"
        for issue in issues
    )


def test_semantic_review_detects_polarity_conflict():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans
    from app.pipeline.semantic_review import semantic_review

    nodes = [
        node("المشروع معتمد وفق المحضر النهائي.", 0),
        node("المشروع غير معتمد وفق النسخة الأخيرة.", 1),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    issues = semantic_review(nodes, memory)

    assert any(
        issue.issue_type == "polarity_conflict"
        for issue in issues
    )


def test_semantic_review_detects_decision_conflict():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans
    from app.pipeline.semantic_review import semantic_review

    nodes = [
        node("تم اعتماد الخطة التشغيلية للمشروع.", 0),
        node("تم إلغاء الخطة التشغيلية للمشروع.", 1),
    ]
    chunks = build_chunks(nodes)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)
    issues = semantic_review(nodes, memory)

    assert any(
        issue.issue_type == "decision_conflict"
        for issue in issues
    )


def test_semantic_fact_conflict_matches_equivalent_capacity_claims():
    from app.pipeline.facts import detect_fact_conflicts, extract_facts

    nodes = [
        node("بلغت الطاقة التشغيلية السنوية للمصنع 2000000 وحدة.", 0),
        node("إجمالي القدرة الإنتاجية للمصنع سنويًا تساوي 1800000 وحدة.", 1),
    ]
    conflicts = detect_fact_conflicts(extract_facts(nodes))

    assert any(
        set(conflict.values) == {"1800000", "2000000"}
        for conflict in conflicts
    )


def test_semantic_fact_conflict_matches_execution_duration():
    from app.pipeline.facts import detect_fact_conflicts, extract_facts

    nodes = [
        node("مدة التنفيذ المعتمدة للمشروع هي 12 شهرًا.", 0),
        node("ينص الجدول الزمني النهائي على إكمال المشروع خلال 18 شهرًا.", 1),
    ]
    conflicts = detect_fact_conflicts(extract_facts(nodes))

    assert any(
        set(conflict.values) == {"12", "18"}
        for conflict in conflicts
    )


def test_semantic_context_matches_delay_paraphrase():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.context import retrieve_context
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans

    nodes = [
        node("تأخر التسليم يستلزم تدخلًا إداريًا مباشرًا.", 0),
        node("نص غير مرتبط لاختبار الفصل.", 1),
        node("تعثر الجدول الزمني يستدعي تصعيد القرار إلى الإدارة التنفيذية.", 2),
    ]
    chunks = build_chunks(nodes, target_tokens=6, hard_limit=12)
    protected = extract_protected_spans(nodes)
    memory = build_document_memory(nodes, chunks, protected)

    package = retrieve_context(
        target_node_id="n-0",
        nodes=nodes,
        chunks=chunks,
        memory=memory,
        query="تأخر التسليم",
        max_chunks=3,
    )

    assert any("تعثر الجدول الزمني" in hit.text for hit in package.hits)

def test_arabic_review_detects_common_orthography_errors():
    issues = fast_review([
        node("هاذا التقرير يوضح مسؤوليه الجهة، لاكن المعلومة صحيحة.", 0)
    ])
    replacements = {issue.replacement for issue in issues}
    assert "هذا" in replacements
    assert "مسؤولية" in replacements
    assert "لكن" in replacements


def test_arabic_review_detects_punctuation_spacing():
    issues = fast_review([
        node("تم اعتماد الخطة ،ثم بدأت المرحلة التالية.", 0)
    ])
    assert any(issue.title == "مسافة قبل علامة ترقيم" for issue in issues)
    assert any(issue.title == "مسافة بعد علامة ترقيم" for issue in issues)


def test_arabic_review_detects_style_redundancy():
    issues = fast_review([
        node("تم تحليل النتائج من خلال استخدام النموذج في الوقت الراهن.", 0)
    ])
    replacements = {issue.replacement for issue in issues}
    assert "باستخدام" in replacements
    assert "حاليًا" in replacements


def test_arabic_review_skips_discretionary_style_in_full_quote():
    issues = fast_review([
        node("«في الوقت الراهن نستخدم هذا التعبير كما ورد في المصدر»", 0)
    ])
    assert not any(issue.category == "style" for issue in issues)


def test_arabic_review_keeps_style_off_headings():
    heading = DocumentNode(
        id="heading-1",
        type="heading",
        text="في الوقت الراهن",
        sequence_no=0,
    )
    issues = fast_review([heading])
    assert not any(issue.category == "style" for issue in issues)


def test_arabic_review_suggestion_ids_are_stable():
    nodes = [node("هاذا التقرير يحتاج إلى مراجعة.", 0)]
    first = fast_review(nodes)
    second = fast_review(nodes)
    assert [issue.id for issue in first] == [issue.id for issue in second]


def test_arabic_review_does_not_flag_clean_sentence():
    issues = fast_review([
        node("تم اعتماد الخطة وفق نتائج الدراسة، وسيبدأ التنفيذ لاحقًا.", 0)
    ])
    assert issues == []

def test_arabic_review_replaces_colon_between_number_and_unit():
    issues = fast_review([
        node("المدة: 8 :أشهر.", 0)
    ])
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


def test_arabic_review_keeps_correct_number_unit_phrase():
    issues = fast_review([
        node("المدة: 6 أشهر.", 0)
    ])
    assert issues == []

def test_parser_preserves_block_anchor_for_evidence():
    from io import BytesIO
    from docx import Document
    from app.pipeline.parser import parse_docx

    document = Document()
    document.add_paragraph("الفقرة الأولى.")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "خلية الاختبار"
    document.add_paragraph("الفقرة الأخيرة.")

    stream = BytesIO()
    document.save(stream)
    nodes = parse_docx(stream.getvalue())

    assert nodes[0].source_anchor["block_index"] == 0
    table_node = next(item for item in nodes if item.type == "table_cell")
    assert table_node.source_anchor["block_index"] == 1
    assert table_node.source_anchor["row"] == 0
    assert table_node.source_anchor["cell"] == 0
    assert nodes[-1].source_anchor["block_index"] == 2

def test_action_policy_allows_only_meaning_lock_safe_auto_fix():
    from app.pipeline.chunker import build_chunks
    from app.pipeline.evidence import build_evidence_traces
    from app.pipeline.memory import build_document_memory
    from app.pipeline.protection import extract_protected_spans
    from app.pipeline.reviewer import fast_review
    from app.pipeline.semantic_review import semantic_review

    nodes = [node("هاذا التقرير معتمد.", 0)]
    protected = extract_protected_spans(nodes)
    suggestions = fast_review(nodes)
    memory = build_document_memory(nodes, build_chunks(nodes), protected)
    traces = build_evidence_traces(
        nodes,
        suggestions=suggestions,
        semantic_issues=semantic_review(nodes, memory),
        memory=memory,
        protected_spans=protected,
    )

    trace = next(
        item for item in traces
        if item.finding_kind == "suggestion"
    )
    assert trace.meaning_lock_status == "PASS"
    assert trace.recommended_action == "auto_fix"
    assert trace.auto_apply_allowed is True


def test_action_policy_blocks_meaning_changing_patch():
    from app.contracts import Suggestion
    from app.pipeline.evidence import build_evidence_traces
    from app.pipeline.protection import extract_protected_spans

    nodes = [node("تبلغ القيمة 100 ريال.", 0)]
    protected = extract_protected_spans(nodes)
    dangerous = Suggestion(
        id="dangerous-test",
        node_id=nodes[0].id,
        category="language",
        title="تعديل",
        explanation="اختبار منع تغيير المعنى.",
        original="100 ريال",
        replacement="100 دولار",
        confidence=0.999,
    )
    trace = build_evidence_traces(
        nodes,
        suggestions=[dangerous],
        protected_spans=protected,
    )[0]

    assert trace.meaning_lock_status == "BLOCK"
    assert trace.recommended_action == "block"
    assert trace.auto_apply_allowed is False


def test_auto_apply_plan_revalidates_stale_suggestion():
    from app.contracts import Suggestion
    from app.pipeline.auto_apply import build_safe_auto_apply_plan
    from app.pipeline.protection import extract_protected_spans

    nodes = [node("هاذا التقرير معتمد.", 0)]
    suggestions = [
        Suggestion(
            id="first-stale",
            node_id=nodes[0].id,
            category="language",
            title="تصحيح",
            explanation="الأول.",
            original="هاذا",
            replacement="هذا",
            confidence=0.995,
            start_offset=0,
            end_offset=len("هاذا"),
        ),
        Suggestion(
            id="second-stale",
            node_id=nodes[0].id,
            category="language",
            title="تصحيح",
            explanation="الثاني.",
            original="هاذا",
            replacement="هذا",
            confidence=0.995,
            start_offset=0,
            end_offset=len("هاذا"),
        ),
    ]
    plan = build_safe_auto_apply_plan(
        nodes,
        suggestions,
        extract_protected_spans(nodes),
    )

    assert len(plan.patches) == 1
    assert any(item.reason == "SOURCE_CHANGED" for item in plan.skipped)

def test_review_loop_converges_and_is_idempotent():
    from io import BytesIO
    from docx import Document
    from app.pipeline.review_loop import run_docx_review_loop

    document = Document()
    document.add_paragraph("هاذا التقرير ،ثم بدأ التنفيذ.")
    stream = BytesIO()
    document.save(stream)

    first = run_docx_review_loop(stream.getvalue())
    assert first.stable is True
    assert first.safety_pass is True
    assert first.initial_auto_fix_count >= 2
    assert first.final_auto_fix_count == 0
    assert not first.new_suggestion_keys
    assert not first.new_high_impact_keys

    second = run_docx_review_loop(first.output)
    assert second.stable is True
    assert second.safety_pass is True
    assert second.initial_auto_fix_count == 0
    assert second.output == first.output


def test_review_loop_preserves_protected_meaning():
    from io import BytesIO
    from docx import Document
    from app.pipeline.review_loop import run_docx_review_loop

    document = Document()
    document.add_paragraph(
        "لا يتحمل الطرف الأول تكاليف النقل ، وفق العقد."
    )
    stream = BytesIO()
    document.save(stream)

    result = run_docx_review_loop(stream.getvalue())
    assert result.stable is True
    assert result.safety_pass is True
    assert result.meaning_preserved is True
    assert result.structure_preserved is True

    output = Document(BytesIO(result.output))
    assert "النقل، وفق العقد" in output.paragraphs[0].text


def test_review_loop_keeps_style_advisory_without_rewriting():
    from io import BytesIO
    from docx import Document
    from app.pipeline.review_loop import run_docx_review_loop

    document = Document()
    document.add_paragraph(
        "تمت المعالجة في الوقت الراهن وفق الإجراء المعتمد."
    )
    stream = BytesIO()
    document.save(stream)
    payload = stream.getvalue()

    result = run_docx_review_loop(payload)
    assert result.stable is True
    assert result.safety_pass is True
    assert result.initial_auto_fix_count == 0
    assert result.final_suggestion_count >= 1
    assert result.output == payload

def test_docx_fidelity_preserves_rich_structure():
    from io import BytesIO
    from docx import Document
    from docx.shared import Inches
    from app.pipeline.auto_apply import build_safe_auto_apply_plan
    from app.pipeline.docx_patch import apply_patches_to_docx
    from app.pipeline.parser import parse_docx
    from app.pipeline.protection import extract_protected_spans
    from app.pipeline.reviewer import fast_review

    document = Document()
    document.sections[0].header.paragraphs[0].text = "رأس ثابت"
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = "خلية ثابتة"
    table.cell(0, 1).text = "قيمة"
    paragraph = document.add_paragraph()
    bold = paragraph.add_run("تنبيه: ")
    bold.bold = True
    paragraph.add_run("هاذا التقرير معتمد.")

    stream = BytesIO()
    document.save(stream)
    payload = stream.getvalue()

    nodes = parse_docx(payload)
    protected = extract_protected_spans(nodes)
    plan = build_safe_auto_apply_plan(
        nodes,
        fast_review(nodes),
        protected,
    )
    output, report = apply_patches_to_docx(
        payload,
        plan.patches,
    )

    assert report.applied
    assert report.fidelity_ok is True
    assert report.fidelity_errors == []

    result = Document(BytesIO(output))
    assert result.sections[0].header.paragraphs[0].text == "رأس ثابت"
    assert result.tables[0].style.name == "Table Grid"
    assert result.paragraphs[-1].runs[0].bold is True
    assert "هذا التقرير معتمد." in result.paragraphs[-1].text


def test_docx_patch_preserves_mixed_run_formatting_across_fix():
    from io import BytesIO
    from docx import Document
    from app.pipeline.auto_apply import build_safe_auto_apply_plan
    from app.pipeline.docx_patch import apply_patches_to_docx
    from app.pipeline.parser import parse_docx
    from app.pipeline.protection import extract_protected_spans
    from app.pipeline.reviewer import fast_review

    document = Document()
    paragraph = document.add_paragraph()
    first = paragraph.add_run("ها")
    second = paragraph.add_run("ذا")
    first.bold = True
    second.italic = True
    paragraph.add_run(" التقرير معتمد.")

    stream = BytesIO()
    document.save(stream)
    payload = stream.getvalue()

    nodes = parse_docx(payload)
    protected = extract_protected_spans(nodes)
    plan = build_safe_auto_apply_plan(
        nodes,
        fast_review(nodes),
        protected,
    )
    output, report = apply_patches_to_docx(
        payload,
        plan.patches,
    )

    assert report.fidelity_ok is True
    result = Document(BytesIO(output))
    runs = result.paragraphs[0].runs
    assert "".join(run.text for run in runs[:2]) == "هذا"
    assert runs[0].bold is True
    assert runs[1].italic is True


def test_docx_patch_fails_closed_on_special_run_span():
    from io import BytesIO
    from docx import Document
    from app.contracts import PatchOperation
    from app.pipeline.docx_patch import apply_patches_to_docx
    from app.pipeline.parser import parse_docx

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("ه")
    special = paragraph.add_run()
    special.add_tab()
    paragraph.add_run("اذا")

    stream = BytesIO()
    document.save(stream)
    payload = stream.getvalue()

    target = parse_docx(payload)[0]
    output, report = apply_patches_to_docx(
        payload,
        [
            PatchOperation(
                node_id=target.id,
                original="ه\tاذا",
                replacement="هذا",
                start_offset=0,
            )
        ],
    )

    assert report.applied == []
    assert report.skipped == [target.id]
    assert report.fidelity_ok is True
    assert output == payload

