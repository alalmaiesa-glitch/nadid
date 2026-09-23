from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import app.docx_security as security
from app.docx_security import UnsafeDocxError, validate_docx_payload


def make_docx(extra_entries: dict[str, bytes] | None = None) -> bytes:
    buffer = BytesIO()

    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types />")
        archive.writestr(
            "word/document.xml",
            b"<w:document xmlns:w='urn:test'><w:body /></w:document>",
        )

        for name, content in (extra_entries or {}).items():
            archive.writestr(name, content)

    return buffer.getvalue()


def test_valid_minimal_docx_passes():
    validate_docx_payload(make_docx())


def test_plain_bytes_are_rejected():
    with pytest.raises(UnsafeDocxError, match="not_a_zip"):
        validate_docx_payload(b"not a docx")


def test_missing_docx_structure_is_rejected():
    buffer = BytesIO()

    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types />")

    with pytest.raises(UnsafeDocxError, match="missing_docx_structure"):
        validate_docx_payload(buffer.getvalue())


def test_zip_path_traversal_is_rejected():
    payload = make_docx({"../escape.txt": b"x"})

    with pytest.raises(UnsafeDocxError, match="unsafe_zip_path"):
        validate_docx_payload(payload)


def test_uncompressed_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(security, "MAX_UNCOMPRESSED_BYTES", 100)
    payload = make_docx({"word/large.xml": b"x" * 200})

    with pytest.raises(UnsafeDocxError, match="uncompressed_size_limit"):
        validate_docx_payload(payload)


def test_word_count_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(security, "MAX_WORD_COUNT", 10)

    with pytest.raises(UnsafeDocxError, match="word_count_limit"):
        security.validate_word_count(11)
