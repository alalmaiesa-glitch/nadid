from __future__ import annotations

from io import BytesIO
from uuid import NAMESPACE_URL, uuid5

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.document import Document as DocumentObject

from app.contracts import DocumentNode


def _iter_blocks(parent: DocumentObject):
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def _heading_level(paragraph: Paragraph) -> int | None:
    style_name = (paragraph.style.name or "").lower()
    if style_name.startswith("heading"):
        suffix = style_name.replace("heading", "").strip()
        try:
            return int(suffix) if suffix else 1
        except ValueError:
            return 1
    return None


def _stable_node_id(
    sequence: int,
    node_type: str,
    text: str,
    anchor: str,
) -> str:
    identity = f"{sequence}|{node_type}|{anchor}|{text}"
    return str(uuid5(NAMESPACE_URL, identity))


def parse_docx(data: bytes) -> list[DocumentNode]:
    document = Document(BytesIO(data))
    nodes: list[DocumentNode] = []
    sequence = 0

    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue

            level = _heading_level(block)
            node_type = "heading" if level else "paragraph"
            style_name = block.style.name if block.style else None
            nodes.append(
                DocumentNode(
                    id=_stable_node_id(
                        sequence,
                        node_type,
                        text,
                        f"paragraph:{style_name}:{level}",
                    ),
                    type=node_type,
                    text=text,
                    sequence_no=sequence,
                    source_anchor={
                        "kind": "paragraph",
                        "style": style_name,
                        "heading_level": level,
                    },
                )
            )
            sequence += 1
            continue

        if isinstance(block, Table):
            for row_index, row in enumerate(block.rows):
                for cell_index, cell in enumerate(row.cells):
                    text = cell.text.strip()
                    if not text:
                        continue
                    nodes.append(
                        DocumentNode(
                            id=_stable_node_id(
                                sequence,
                                "table_cell",
                                text,
                                f"table:{row_index}:{cell_index}",
                            ),
                            type="table_cell",
                            text=text,
                            sequence_no=sequence,
                            source_anchor={
                                "kind": "table_cell",
                                "row": row_index,
                                "cell": cell_index,
                            },
                        )
                    )
                    sequence += 1

    return nodes
