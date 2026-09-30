from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from lxml import etree

from app.contracts import PatchOperation
from app.pipeline.parser import parse_docx


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


@dataclass(frozen=True)
class FidelityReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_package(data: bytes) -> dict[str, bytes]:
    try:
        with ZipFile(BytesIO(data), "r") as archive:
            return {
                name: archive.read(name)
                for name in archive.namelist()
                if not name.endswith("/")
            }
    except BadZipFile as exc:
        raise ValueError("Invalid DOCX ZIP package.") from exc


def _c14n_xml(data: bytes) -> bytes:
    parser = etree.XMLParser(
        remove_blank_text=False,
        resolve_entities=False,
        no_network=True,
    )
    root = etree.fromstring(data, parser=parser)
    return etree.tostring(root, method="c14n")


def _document_structure(data: bytes) -> bytes:
    parser = etree.XMLParser(
        remove_blank_text=False,
        resolve_entities=False,
        no_network=True,
    )
    root = etree.fromstring(data, parser=parser)
    cloned = deepcopy(root)

    for element in cloned.iter():
        if element.tag == f"{{{W_NS}}}t":
            element.text = ""
            element.attrib.pop(f"{{{XML_NS}}}space", None)

    return etree.tostring(cloned, method="c14n")


def _relationship_signature(parts: dict[str, bytes]) -> tuple:
    relationships: list[tuple[str, tuple]] = []

    for name, payload in parts.items():
        if not name.endswith(".rels"):
            continue
        root = etree.fromstring(payload)
        rows = []
        for relation in root:
            if relation.tag != f"{{{REL_NS}}}Relationship":
                continue
            rows.append(
                (
                    relation.get("Id") or "",
                    relation.get("Type") or "",
                    relation.get("Target") or "",
                    relation.get("TargetMode") or "",
                )
            )
        relationships.append((name, tuple(sorted(rows))))

    return tuple(sorted(relationships))


def _content_type_signature(payload: bytes) -> tuple:
    root = etree.fromstring(payload)
    defaults = []
    overrides = []

    for element in root:
        if element.tag == f"{{{CT_NS}}}Default":
            defaults.append(
                (
                    element.get("Extension") or "",
                    element.get("ContentType") or "",
                )
            )
        elif element.tag == f"{{{CT_NS}}}Override":
            overrides.append(
                (
                    element.get("PartName") or "",
                    element.get("ContentType") or "",
                )
            )

    return tuple(sorted(defaults)), tuple(sorted(overrides))


def _immutable_part(name: str) -> bool:
    path = PurePosixPath(name)
    if name == "word/document.xml":
        return False
    if name.startswith("docProps/"):
        return False
    if name.endswith(".rels"):
        return False
    if name == "[Content_Types].xml":
        return False

    # All package parts other than the main document and metadata are expected
    # to survive a text-only Nadid patch semantically unchanged.
    return (
        name.startswith("word/")
        or name.startswith("customXml/")
        or name.startswith("custom/")
        or path.suffix.lower() not in {".xml"}
    )


def _immutable_signature(
    parts: dict[str, bytes],
) -> dict[str, str]:
    output: dict[str, str] = {}

    for name, payload in parts.items():
        if not _immutable_part(name):
            continue
        if name.lower().endswith(".xml"):
            output[name] = _sha256(_c14n_xml(payload))
        else:
            output[name] = _sha256(payload)

    return output


def _expected_text_after(
    source: str,
    patches: list[PatchOperation],
) -> str | None:
    working = source
    indexed = list(enumerate(patches))
    indexed.sort(
        key=lambda item: (
            item[1].start_offset is None,
            -(
                item[1].start_offset
                if item[1].start_offset is not None
                else -1
            ),
            item[0],
        )
    )

    for _, patch in indexed:
        if patch.start_offset is None:
            index = working.find(patch.original)
            if index < 0:
                return None
        else:
            index = patch.start_offset
            end = index + len(patch.original)
            if (
                index < 0
                or end > len(working)
                or working[index:end] != patch.original
            ):
                return None

        end = index + len(patch.original)
        working = (
            working[:index]
            + patch.replacement
            + working[end:]
        )

    return working


def _text_changes_are_exact(
    before: bytes,
    after: bytes,
    patches: list[PatchOperation],
) -> tuple[bool, list[str]]:
    before_nodes = parse_docx(before)
    after_nodes = parse_docx(after)
    errors: list[str] = []

    before_map = {node.id: node for node in before_nodes}
    after_map = {node.id: node for node in after_nodes}

    if set(before_map) != set(after_map):
        return False, ["NODE_IDENTITY_CHANGED"]

    by_node: dict[str, list[PatchOperation]] = {}
    for patch in patches:
        by_node.setdefault(patch.node_id, []).append(patch)

    for node_id, before_node in before_map.items():
        after_node = after_map[node_id]
        node_patches = by_node.get(node_id, [])

        if not node_patches:
            if after_node.text != before_node.text:
                errors.append(
                    f"UNEXPECTED_TEXT_CHANGE:{node_id}"
                )
            continue

        expected = _expected_text_after(
            before_node.text,
            node_patches,
        )
        if expected is None:
            errors.append(
                f"EXPECTED_PATCH_SOURCE_MISMATCH:{node_id}"
            )
            continue
        if after_node.text != expected:
            errors.append(
                f"PATCH_TEXT_MISMATCH:{node_id}"
            )

    unknown_patch_nodes = set(by_node) - set(before_map)
    for node_id in sorted(unknown_patch_nodes):
        errors.append(f"PATCH_NODE_NOT_FOUND:{node_id}")

    return not errors, errors


def verify_docx_fidelity(
    before: bytes,
    after: bytes,
    patches: list[PatchOperation],
) -> FidelityReport:
    """
    Verify text-only DOCX round-trip fidelity.

    This is intentionally fail-closed. A Nadid text patch may change only
    expected text in word/document.xml. Package relationships, content types,
    media/embedded payloads, styles, numbering, settings, headers/footers,
    notes, themes and the non-text XML structure of document.xml must remain
    unchanged.
    """
    errors: list[str] = []
    checks: dict[str, bool] = {}

    try:
        before_parts = _read_package(before)
        after_parts = _read_package(after)
    except ValueError:
        return FidelityReport(
            ok=False,
            errors=["INVALID_DOCX_PACKAGE"],
            checks={"valid_package": False},
        )

    checks["valid_package"] = True

    same_parts = set(before_parts) == set(after_parts)
    checks["package_parts_preserved"] = same_parts
    if not same_parts:
        missing = sorted(set(before_parts) - set(after_parts))
        added = sorted(set(after_parts) - set(before_parts))
        if missing:
            errors.append(
                "PACKAGE_PARTS_REMOVED:" + ",".join(missing)
            )
        if added:
            errors.append(
                "PACKAGE_PARTS_ADDED:" + ",".join(added)
            )

    rels_ok = (
        _relationship_signature(before_parts)
        == _relationship_signature(after_parts)
    )
    checks["relationships_preserved"] = rels_ok
    if not rels_ok:
        errors.append("RELATIONSHIPS_CHANGED")

    before_ct = before_parts.get("[Content_Types].xml")
    after_ct = after_parts.get("[Content_Types].xml")
    content_types_ok = bool(
        before_ct
        and after_ct
        and _content_type_signature(before_ct)
        == _content_type_signature(after_ct)
    )
    checks["content_types_preserved"] = content_types_ok
    if not content_types_ok:
        errors.append("CONTENT_TYPES_CHANGED")

    immutable_ok = (
        _immutable_signature(before_parts)
        == _immutable_signature(after_parts)
    )
    checks["immutable_parts_preserved"] = immutable_ok
    if not immutable_ok:
        before_sig = _immutable_signature(before_parts)
        after_sig = _immutable_signature(after_parts)
        changed = sorted(
            name
            for name in set(before_sig) | set(after_sig)
            if before_sig.get(name) != after_sig.get(name)
        )
        errors.append(
            "IMMUTABLE_PARTS_CHANGED:" + ",".join(changed)
        )

    before_doc = before_parts.get("word/document.xml")
    after_doc = after_parts.get("word/document.xml")
    structure_ok = bool(
        before_doc
        and after_doc
        and _document_structure(before_doc)
        == _document_structure(after_doc)
    )
    checks["document_structure_preserved"] = structure_ok
    if not structure_ok:
        errors.append("DOCUMENT_STRUCTURE_CHANGED")

    text_ok, text_errors = _text_changes_are_exact(
        before,
        after,
        patches,
    )
    checks["text_changes_exact"] = text_ok
    errors.extend(text_errors)

    return FidelityReport(
        ok=not errors,
        errors=errors,
        checks=checks,
    )
