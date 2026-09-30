from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.contracts import PatchOperation
from app.pipeline.docx_fidelity import verify_docx_fidelity
from app.pipeline.parser import _heading_level, _iter_blocks, _stable_node_id


@dataclass
class ApplyReport:
    applied: list[str]
    skipped: list[str]
    fidelity_ok: bool = True
    fidelity_errors: list[str] | None = None


def _run_text_element(run):
    children = list(run._r)
    text_elements = [
        child
        for child in children
        if child.tag.endswith("}t")
    ]
    non_text = [
        child
        for child in children
        if not (
            child.tag.endswith("}rPr")
            or child.tag.endswith("}t")
        )
    ]
    if non_text or len(text_elements) != 1:
        return None
    return text_elements[0]


def _set_run_text_preserving_structure(run, text: str) -> bool:
    element = _run_text_element(run)
    if element is None:
        return False

    element.text = text
    space_key = "{http://www.w3.org/XML/1998/namespace}space"
    if text.startswith(" ") or text.endswith(" "):
        element.set(space_key, "preserve")
    else:
        element.attrib.pop(space_key, None)

    return True


def _replace_across_runs(
    paragraph: Paragraph,
    original: str,
    replacement: str,
    start_offset: int | None = None,
) -> bool:
    full_text = "".join(run.text for run in paragraph.runs)

    if start_offset is None:
        start = full_text.find(original)
        if start < 0:
            return False
    else:
        start = start_offset
        if (
            start < 0
            or start + len(original) > len(full_text)
            or full_text[start:start + len(original)] != original
        ):
            return False

    end = start + len(original)
    cursor = 0
    start_run = None
    end_run = None
    start_in_run = 0
    end_in_run = 0
    run_ranges: list[tuple[int, int]] = []

    for index, run in enumerate(paragraph.runs):
        run_start = cursor
        run_end = cursor + len(run.text)
        run_ranges.append((run_start, run_end))

        if start_run is None and run_start <= start < run_end:
            start_run = index
            start_in_run = start - run_start

        if run_start < end <= run_end:
            end_run = index
            end_in_run = end - run_start
            break

        cursor = run_end

    if start_run is None or end_run is None:
        return False

    touched = paragraph.runs[start_run:end_run + 1]
    if any(_run_text_element(run) is None for run in touched):
        # Fail closed around tabs, breaks, drawings, fields, hyperlinks or
        # multi-text-node runs. A text correction must not flatten structure.
        return False

    if start_run == end_run:
        run = paragraph.runs[start_run]
        return _set_run_text_preserving_structure(
            run,
            (
                run.text[:start_in_run]
                + replacement
                + run.text[end_in_run:]
            ),
        )

    segment_lengths: list[int] = []
    for index in range(start_run, end_run + 1):
        run_start, run_end = run_ranges[index]
        segment_start = max(start, run_start)
        segment_end = min(end, run_end)
        segment_lengths.append(max(0, segment_end - segment_start))

    assigned: list[str] = []
    remaining = replacement
    for index, length in enumerate(segment_lengths):
        if index == len(segment_lengths) - 1:
            assigned.append(remaining)
            remaining = ""
        else:
            take = min(length, len(remaining))
            assigned.append(remaining[:take])
            remaining = remaining[take:]

    first = paragraph.runs[start_run]
    last = paragraph.runs[end_run]
    replacement_texts: list[str] = []

    for offset, run in enumerate(touched):
        if offset == 0:
            value = run.text[:start_in_run] + assigned[offset]
        elif offset == len(touched) - 1:
            value = assigned[offset] + run.text[end_in_run:]
        else:
            value = assigned[offset]
        replacement_texts.append(value)

    for run, value in zip(touched, replacement_texts):
        if not _set_run_text_preserving_structure(run, value):
            return False

    return True


def _apply_to_cell(
    cell,
    original: str,
    replacement: str,
    start_offset: int | None = None,
) -> bool:
    if start_offset is None:
        for paragraph in cell.paragraphs:
            if original in paragraph.text:
                return _replace_across_runs(
                    paragraph,
                    original,
                    replacement,
                )
        return False

    cursor = 0
    target_end = start_offset + len(original)
    for paragraph in cell.paragraphs:
        paragraph_start = cursor
        paragraph_end = cursor + len(paragraph.text)

        if (
            paragraph_start <= start_offset
            and target_end <= paragraph_end
        ):
            local_start = start_offset - paragraph_start
            return _replace_across_runs(
                paragraph,
                original,
                replacement,
                start_offset=local_start,
            )

        # python-docx cell.text separates paragraphs with a newline.
        cursor = paragraph_end + 1

    return False


def apply_patches_to_docx(
    data: bytes,
    patches: list[PatchOperation],
) -> tuple[bytes, ApplyReport]:
    if not patches:
        return data, ApplyReport(
            applied=[],
            skipped=[],
            fidelity_ok=True,
            fidelity_errors=[],
        )

    document = Document(BytesIO(data))
    patch_map: dict[str, list[PatchOperation]] = {}

    for patch in patches:
        patch_map.setdefault(patch.node_id, []).append(patch)

    for node_id, node_patches in patch_map.items():
        indexed = list(enumerate(node_patches))
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
        patch_map[node_id] = [item[1] for item in indexed]

    applied: list[str] = []
    applied_patches: list[PatchOperation] = []
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
                full_start = (
                    patch.start_offset
                    + len(block.text)
                    - len(block.text.lstrip())
                    if patch.start_offset is not None
                    else None
                )
                if _replace_across_runs(
                    block,
                    patch.original,
                    patch.replacement,
                    start_offset=full_start,
                ):
                    applied.append(patch.node_id)
                    applied_patches.append(patch)
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
                        full_start = (
                            patch.start_offset
                            + len(cell.text)
                            - len(cell.text.lstrip())
                            if patch.start_offset is not None
                            else None
                        )
                        if _apply_to_cell(
                            cell,
                            patch.original,
                            patch.replacement,
                            start_offset=full_start,
                        ):
                            applied.append(patch.node_id)
                            applied_patches.append(patch)
                        else:
                            skipped.append(patch.node_id)

                    sequence += 1

    if not applied_patches:
        return data, ApplyReport(
            applied=applied,
            skipped=skipped,
            fidelity_ok=True,
            fidelity_errors=[],
        )

    output = BytesIO()
    document.save(output)
    output_data = output.getvalue()

    fidelity = verify_docx_fidelity(
        data,
        output_data,
        applied_patches,
    )

    return output_data, ApplyReport(
        applied=applied,
        skipped=skipped,
        fidelity_ok=fidelity.ok,
        fidelity_errors=fidelity.errors,
    )
