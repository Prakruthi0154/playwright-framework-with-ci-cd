import csv
import io
from pathlib import PurePath
from zipfile import BadZipFile

from docx import Document
from fastapi import HTTPException, UploadFile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import settings

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx"}


async def extract_document_text(file: UploadFile) -> tuple[str, str]:
    filename = PurePath(file.filename or "upload").name
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Supported formats are PDF, DOCX, TXT, CSV, and XLSX")
    content = await file.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise HTTPException(413, "Uploaded file exceeds the configured size limit")
    if not content:
        raise HTTPException(422, "Uploaded file is empty")
    try:
        if extension == ".pdf":
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages
            )
        elif extension == ".docx":
            text = "\n".join(
                paragraph.text for paragraph in Document(io.BytesIO(content)).paragraphs
            )
        elif extension == ".txt":
            text = content.decode("utf-8-sig")
        elif extension == ".csv":
            rows = csv.reader(io.StringIO(content.decode("utf-8-sig")))
            text = "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)
        else:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            text = "\n".join(
                " | ".join(str(cell) for cell in row if cell is not None)
                for sheet in workbook.worksheets
                for row in sheet.iter_rows(values_only=True)
            )
            workbook.close()
    except (
        ValueError,
        UnicodeDecodeError,
        OSError,
        BadZipFile,
        PdfReadError,
        InvalidFileException,
    ) as exc:
        raise HTTPException(422, "The uploaded document could not be parsed") from exc
    text = text.strip()
    if not text:
        raise HTTPException(422, "No readable text was found in the uploaded document")
    return filename[:255], text[:100000]
