from __future__ import annotations

from io import BytesIO
from urllib.parse import urlsplit
from xml.parsers import expat
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile, is_zipfile


MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ZIP_ENTRIES = 20_000
MAX_SINGLE_ENTRY_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 2_000.0
MAX_WORD_COUNT = 500_000

# XML is the executable-complexity surface of OOXML. These limits are
# deliberately separate from media/package limits because XML is parsed into
# in-memory trees by downstream libraries.
MAX_XML_ENTRY_BYTES = 32 * 1024 * 1024
MAX_TOTAL_XML_BYTES = 96 * 1024 * 1024
MAX_XML_DEPTH = 128
MAX_XML_ELEMENTS = 1_000_000
MAX_XML_ATTRIBUTES_PER_ELEMENT = 256

_REQUIRED_DOCX_ENTRIES = {
    "[Content_Types].xml",
    "word/document.xml",
}

_BLOCKED_PART_PREFIXES = (
    "word/activex/",
    "word/embeddings/",
    "word/controls/",
    "customui/",
)
_BLOCKED_PART_NAMES = {
    "word/vbaproject.bin",
    "word/vbaprojectsignature.bin",
    "word/vbadata.xml",
}
_BLOCKED_CONTENT_TYPE_TOKENS = (
    "macroenabled",
    "vbaproject",
    "activex",
    "oleobject",
)
_BLOCKED_RELATIONSHIP_TYPE_TOKENS = (
    "oleobject",
    "attachedtemplate",
    "vbaproject",
    "/control",
)
_ALLOWED_EXTERNAL_HYPERLINK_SCHEMES = {
    "http",
    "https",
    "mailto",
}

_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


class UnsafeDocxError(ValueError):
    pass


def _normalized_part_name(name: str) -> str:
    return name.replace("\\", "/").lstrip("/").lower()


def _is_xml_part(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".xml") or lower.endswith(".rels")


def _validate_part_policy(names: set[str]) -> None:
    normalized = {_normalized_part_name(name) for name in names}

    for name in normalized:
        if name in _BLOCKED_PART_NAMES:
            raise UnsafeDocxError("active_content_part")
        if any(name.startswith(prefix) for prefix in _BLOCKED_PART_PREFIXES):
            raise UnsafeDocxError("active_content_part")


def _validate_xml_complexity(payload: bytes) -> None:
    depth = 0
    elements = 0

    parser = expat.ParserCreate()

    def start_element(_name, attrs):
        nonlocal depth, elements
        depth += 1
        elements += 1

        if depth > MAX_XML_DEPTH:
            raise UnsafeDocxError("xml_depth_limit")
        if elements > MAX_XML_ELEMENTS:
            raise UnsafeDocxError("xml_element_limit")
        if len(attrs) > MAX_XML_ATTRIBUTES_PER_ELEMENT:
            raise UnsafeDocxError("xml_attribute_limit")

    def end_element(_name):
        nonlocal depth
        depth -= 1

    def reject_doctype(*_args):
        raise UnsafeDocxError("xml_dtd_or_entity")

    def reject_entity(*_args):
        raise UnsafeDocxError("xml_dtd_or_entity")

    def reject_external_entity(*_args):
        raise UnsafeDocxError("xml_dtd_or_entity")

    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.EntityDeclHandler = reject_entity
    parser.ExternalEntityRefHandler = reject_external_entity

    try:
        parser.Parse(payload, True)
    except UnsafeDocxError:
        raise
    except expat.ExpatError as exc:
        raise UnsafeDocxError("invalid_xml_part") from exc


def _parse_xml(payload: bytes):
    # XML complexity and DTD/entity policy has already been checked before
    # ElementTree sees the bytes.
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise UnsafeDocxError("invalid_xml_part") from exc


def _validate_content_types(payload: bytes) -> None:
    root = _parse_xml(payload)

    for element in root:
        if element.tag not in {
            f"{{{_CT_NS}}}Default",
            f"{{{_CT_NS}}}Override",
        }:
            continue
        content_type = (element.get("ContentType") or "").lower()
        if any(
            token in content_type
            for token in _BLOCKED_CONTENT_TYPE_TOKENS
        ):
            raise UnsafeDocxError("active_content_type")


def _validate_relationships(payload: bytes) -> None:
    root = _parse_xml(payload)

    for relation in root:
        if relation.tag != f"{{{_REL_NS}}}Relationship":
            continue

        rel_type = (relation.get("Type") or "").lower()
        target_mode = (relation.get("TargetMode") or "").lower()
        target = (relation.get("Target") or "").strip()

        if any(
            token in rel_type
            for token in _BLOCKED_RELATIONSHIP_TYPE_TOKENS
        ):
            raise UnsafeDocxError("active_content_relationship")

        if target_mode != "external":
            continue

        if not rel_type.endswith("/hyperlink"):
            raise UnsafeDocxError("unsafe_external_relationship")

        scheme = urlsplit(target).scheme.lower()
        if scheme not in _ALLOWED_EXTERNAL_HYPERLINK_SCHEMES:
            raise UnsafeDocxError(
                "unsafe_external_hyperlink_scheme"
            )


def validate_docx_payload(data: bytes) -> None:
    if not data:
        raise UnsafeDocxError("empty_file")

    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsafeDocxError("compressed_size_limit")

    stream = BytesIO(data)

    if not is_zipfile(stream):
        raise UnsafeDocxError("not_a_zip")

    stream.seek(0)

    try:
        with ZipFile(stream) as archive:
            entries = archive.infolist()

            if len(entries) > MAX_ZIP_ENTRIES:
                raise UnsafeDocxError("too_many_zip_entries")

            names = {entry.filename for entry in entries}

            if len(names) != len(entries):
                raise UnsafeDocxError("duplicate_zip_entry")

            if not _REQUIRED_DOCX_ENTRIES.issubset(names):
                raise UnsafeDocxError("missing_docx_structure")

            _validate_part_policy(names)

            total_uncompressed = 0
            total_xml_bytes = 0
            xml_payloads: dict[str, bytes] = {}

            for entry in entries:
                if entry.flag_bits & 0x1:
                    raise UnsafeDocxError("encrypted_zip_entry")

                normalized = entry.filename.replace("\\", "/")

                if normalized.startswith("/") or ".." in normalized.split("/"):
                    raise UnsafeDocxError("unsafe_zip_path")

                if entry.file_size > MAX_SINGLE_ENTRY_BYTES:
                    raise UnsafeDocxError("single_entry_size_limit")

                total_uncompressed += entry.file_size

                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise UnsafeDocxError("uncompressed_size_limit")

                if entry.compress_size > 0:
                    ratio = entry.file_size / entry.compress_size

                    if ratio > MAX_COMPRESSION_RATIO:
                        raise UnsafeDocxError("suspicious_compression_ratio")

                if not _is_xml_part(entry.filename):
                    continue

                if entry.file_size > MAX_XML_ENTRY_BYTES:
                    raise UnsafeDocxError("xml_entry_size_limit")

                total_xml_bytes += entry.file_size
                if total_xml_bytes > MAX_TOTAL_XML_BYTES:
                    raise UnsafeDocxError("xml_total_size_limit")

                payload = archive.read(entry)
                _validate_xml_complexity(payload)
                xml_payloads[entry.filename] = payload

            content_types = xml_payloads.get("[Content_Types].xml")
            if content_types is None:
                raise UnsafeDocxError("missing_docx_structure")
            _validate_content_types(content_types)

            for name, payload in xml_payloads.items():
                if name.lower().endswith(".rels"):
                    _validate_relationships(payload)

    except UnsafeDocxError:
        raise
    except BadZipFile as exc:
        raise UnsafeDocxError("invalid_zip") from exc
    except (RuntimeError, OSError, ValueError) as exc:
        raise UnsafeDocxError("invalid_zip") from exc


def validate_word_count(word_count: int) -> None:
    if word_count > MAX_WORD_COUNT:
        raise UnsafeDocxError("word_count_limit")
