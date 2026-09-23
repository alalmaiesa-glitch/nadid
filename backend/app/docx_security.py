from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile, is_zipfile


MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ZIP_ENTRIES = 20_000
MAX_SINGLE_ENTRY_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 2_000.0
MAX_WORD_COUNT = 500_000

_REQUIRED_DOCX_ENTRIES = {
    "[Content_Types].xml",
    "word/document.xml",
}


class UnsafeDocxError(ValueError):
    pass


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

            if not _REQUIRED_DOCX_ENTRIES.issubset(names):
                raise UnsafeDocxError("missing_docx_structure")

            total_uncompressed = 0

            for entry in entries:
                if entry.flag_bits & 0x1:
                    raise UnsafeDocxError("encrypted_zip_entry")

                normalized = entry.filename.replace("\\", "/")

                if normalized.startswith("/") or "../" in normalized.split("/"):
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
    except BadZipFile as exc:
        raise UnsafeDocxError("invalid_zip") from exc


def validate_word_count(word_count: int) -> None:
    if word_count > MAX_WORD_COUNT:
        raise UnsafeDocxError("word_count_limit")
