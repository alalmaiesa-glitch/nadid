from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.contracts import PatchOperation
from app.pipeline.parser import _heading_level, _iter_blocks, _stable_node_id


@dataclass
class ApplyReport:
    applied: list[str]
    skipped: list[str]


def _replace_across_runs(
    paragraph: Paragraph,
    original: str,
    replacement: str,
) -> bool:
    full_text = "".join(run.text for run in paragraph.runs)
    start = full_text.find(original)

    if start < 0:
        return False

    end = start + len(original)
    cursor = 0
    start_run = None
    end_run = None
    start_offset = 0
    end_offset = 0

    for index, run in enumerate(paragraph.runs):
        run_start = cursor
        run_end = cursor + len(run.text)

        if start_run is None and run_start <= start < run_end:
            start_run = index
            start_offset = start - run_start

        if run_start < end <= run_end:
            end_run = index
            end_offset = end - run_start
            break

        cursor = run_end

    if start_run is None or end_run is None:
        return False

    if start_run == end_run:
        run = paragraph.runs[start_run]
        run.text = (
            run.text[:start_offset]
            + replacement
            + run.text[end_offset:]
        )
        return True

    first = paragraph.runs[start_run]
    last = paragraph.runs[end_run]

    prefix = first.text[:start_offset]
    suffix = last.text[end_offset:]

    first.text = prefix + replacement

    for index in range(start_run + 1, end_run):
        paragraph.runs[index].text = ""

    last.text = suffix
    return True


def _apply_to_cell(cell, original: str, replacement: str) -> bool:
    for paragraph in cell.paragraphs:
        if original in paragraph.text:
            return _replace_across_runs(paragraph, original, replacement)

    return False


def apply_patches_to_docx(
    data: bytes,
    patches: list[PatchOperation],
) -> tuple[bytes, ApplyReport]:
    document = Document(BytesIO(data))
    patch_map: dict[str, list[PatchOperation]] = {}

    for patch in patches:
        patch_map.setdefault(patch.node_id, []).append(patch)

    applied: list[str] = []
    skipped: list[str] = []
    sequence = 0

    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue

            level = _heading_level(block)
            node_type = "heading" if level else "paragraph"
            style_name = block.style.name if block.style else None
            node_id = _stable_node_id(
                sequence,
                node_type,
                text,
                f"paragraph:{style_name}:{level}",
            )

            for patch in patch_map.get(node_id, []):
                if _replace_across_runs(
                    block,
                    patch.original,
                    patch.replacement,
                ):
                    applied.append(patch.node_id)
                else:
                    skipped.append(patch.node_id)

            sequence += 1
            continue

        if isinstance(block, Table):
            for row_index, row in enumerate(block.rows):
                for cell_index, cell in enumerate(row.cells):
                    text = cell.text.strip()
                    if not text:
                        continue

                    node_id = _stable_node_id(
                        sequence,
                        "table_cell",
                        text,
                        f"table:{row_index}:{cell_index}",
                    )

                    for patch in patch_map.get(node_id, []):
                        if _apply_to_cell(
                            cell,
                            patch.original,
                            patch.replacement,
                        ):
                            applied.append(patch.node_id)
                        else:
                            skipped.append(patch.node_id)

                    sequence += 1

    output = BytesIO()
    document.save(output)

    return output.getvalue(), ApplyReport(
        applied=applied,
        skipped=skipped,
    )
