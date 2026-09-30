from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document

import app.docx_security as security
from app.docx_security import UnsafeDocxError, validate_docx_payload


def _valid_docx() -> bytes:
    document = Document()
    document.add_paragraph("مستند آمن لاختبار حزمة OOXML.")
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def _rewrite(
    payload: bytes,
    replacements: dict[str, bytes] | None = None,
    additions: dict[str, bytes] | None = None,
) -> bytes:
    replacements = replacements or {}
    additions = additions or {}
    output = BytesIO()

    with ZipFile(BytesIO(payload), "r") as source:
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as target:
            for info in source.infolist():
                target.writestr(
                    info.filename,
                    replacements.get(
                        info.filename,
                        source.read(info.filename),
                    ),
                )
            for name, value in additions.items():
                target.writestr(name, value)

    return output.getvalue()


def _inject_relationship(
    payload: bytes,
    rel_type: str,
    target: str,
    target_mode: str = "External",
) -> bytes:
    rel_name = "word/_rels/document.xml.rels"

    with ZipFile(BytesIO(payload), "r") as archive:
        rels = archive.read(rel_name)

    marker = b"</Relationships>"
    relation = (
        '<Relationship Id="rIdSecurityTest" '
        f'Type="{rel_type}" Target="{target}" '
        f'TargetMode="{target_mode}"/>'
    ).encode("utf-8")

    return _rewrite(
        payload,
        {
            rel_name: rels.replace(
                marker,
                relation + marker,
            )
        },
    )


def test_standard_docx_passes_security_gate():
    validate_docx_payload(_valid_docx())


@pytest.mark.parametrize(
    "part_name",
    [
        "word/vbaProject.bin",
        "word/activeX/activeX1.bin",
        "word/embeddings/oleObject1.bin",
        "customUI/customUI.xml",
    ],
)
def test_active_content_parts_are_rejected(part_name):
    payload = _rewrite(
        _valid_docx(),
        additions={part_name: b"blocked"},
    )

    with pytest.raises(UnsafeDocxError, match="active_content_part"):
        validate_docx_payload(payload)


def test_macro_enabled_content_type_is_rejected():
    payload = _valid_docx()

    with ZipFile(BytesIO(payload), "r") as archive:
        content_types = archive.read("[Content_Types].xml")

    modified = content_types.replace(
        b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        b"application/vnd.ms-word.document.macroEnabled.main+xml",
    )
    payload = _rewrite(
        payload,
        {"[Content_Types].xml": modified},
    )

    with pytest.raises(UnsafeDocxError, match="active_content_type"):
        validate_docx_payload(payload)


def test_external_template_relationship_is_rejected():
    payload = _inject_relationship(
        _valid_docx(),
        (
            "http://schemas.openxmlformats.org/officeDocument/"
            "2006/relationships/attachedTemplate"
        ),
        "https://example.com/template.dotm",
    )

    with pytest.raises(
        UnsafeDocxError,
        match="active_content_relationship",
    ):
        validate_docx_payload(payload)


def test_external_image_relationship_is_rejected():
    payload = _inject_relationship(
        _valid_docx(),
        (
            "http://schemas.openxmlformats.org/officeDocument/"
            "2006/relationships/image"
        ),
        "https://example.com/image.png",
    )

    with pytest.raises(
        UnsafeDocxError,
        match="unsafe_external_relationship",
    ):
        validate_docx_payload(payload)


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com/reference",
        "http://example.com/reference",
        "mailto:editor@example.com",
    ],
)
def test_safe_external_hyperlink_schemes_are_allowed(target):
    payload = _inject_relationship(
        _valid_docx(),
        (
            "http://schemas.openxmlformats.org/officeDocument/"
            "2006/relationships/hyperlink"
        ),
        target,
    )
    validate_docx_payload(payload)


@pytest.mark.parametrize(
    "target",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "javascript:alert(1)",
    ],
)
def test_unsafe_external_hyperlink_schemes_are_rejected(target):
    payload = _inject_relationship(
        _valid_docx(),
        (
            "http://schemas.openxmlformats.org/officeDocument/"
            "2006/relationships/hyperlink"
        ),
        target,
    )

    with pytest.raises(
        UnsafeDocxError,
        match="unsafe_external_hyperlink_scheme",
    ):
        validate_docx_payload(payload)


def test_xml_doctype_is_rejected():
    payload = _valid_docx()
    malicious_xml = b"""<?xml version="1.0"?>
<!DOCTYPE w:document [
  <!ENTITY x "expanded">
]>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body>
</w:document>"""
    payload = _rewrite(
        payload,
        {"word/document.xml": malicious_xml},
    )

    with pytest.raises(UnsafeDocxError, match="xml_dtd_or_entity"):
        validate_docx_payload(payload)


def test_xml_depth_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(security, "MAX_XML_DEPTH", 8)
    nested = (
        b'<?xml version="1.0"?><root>'
        + b"<n>" * 12
        + b"text"
        + b"</n>" * 12
        + b"</root>"
    )
    payload = _rewrite(
        _valid_docx(),
        {"word/document.xml": nested},
    )

    with pytest.raises(UnsafeDocxError, match="xml_depth_limit"):
        validate_docx_payload(payload)


def test_xml_element_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(security, "MAX_XML_ELEMENTS", 10)
    xml = (
        b'<?xml version="1.0"?><root>'
        + b"<n/>" * 20
        + b"</root>"
    )
    payload = _rewrite(
        _valid_docx(),
        {"word/document.xml": xml},
    )

    with pytest.raises(UnsafeDocxError, match="xml_element_limit"):
        validate_docx_payload(payload)


def test_xml_attribute_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(
        security,
        "MAX_XML_ATTRIBUTES_PER_ELEMENT",
        4,
    )
    xml = b'<root a="1" b="2" c="3" d="4" e="5"/>'
    payload = _rewrite(
        _valid_docx(),
        {"word/document.xml": xml},
    )

    with pytest.raises(UnsafeDocxError, match="xml_attribute_limit"):
        validate_docx_payload(payload)


def test_xml_entry_size_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(security, "MAX_XML_ENTRY_BYTES", 64)
    payload = _rewrite(
        _valid_docx(),
        {"word/document.xml": b"<root>" + b"x" * 100 + b"</root>"},
    )

    with pytest.raises(UnsafeDocxError, match="xml_entry_size_limit"):
        validate_docx_payload(payload)


def test_total_xml_size_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(security, "MAX_TOTAL_XML_BYTES", 256)
    payload = _rewrite(
        _valid_docx(),
        additions={
            "word/security-a.xml": b"<a>" + b"x" * 120 + b"</a>",
            "word/security-b.xml": b"<b>" + b"x" * 120 + b"</b>",
        },
    )

    with pytest.raises(UnsafeDocxError, match="xml_total_size_limit"):
        validate_docx_payload(payload)
