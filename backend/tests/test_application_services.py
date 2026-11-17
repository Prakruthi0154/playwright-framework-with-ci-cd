import asyncio
import io
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi import UploadFile
from openpyxl import Workbook, load_workbook
from pydantic import ValidationError
from reportlab.pdfgen.canvas import Canvas

from app.application.ai_generation import (
    AIProviderError,
    OpenAIProvider,
    build_prompt,
    validate_generated_cases,
)
from app.application.document_parser import extract_document_text
from app.application.exports import export_cases
from app.application.security import hash_password, verify_password
from app.config import settings
from app.models.entities import TestCase as CaseEntity


def valid_ai_case(scenario="Valid login"):
    return {
        "scenario": scenario,
        "preconditions": "User is on the sign-in page",
        "steps": ["Enter valid credentials", "Submit the form"],
        "expected_result": "The user is authenticated and sees the dashboard",
        "test_data": {"email": "qa@example.test"},
        "priority": "P1",
        "severity": "medium",
        "test_type": "positive",
        "automation_feasibility": "high",
        "tags": ["authentication"],
    }


def test_password_hash_is_not_the_password_and_verifies():
    hashed = hash_password("StrongPass!234")
    assert hashed != "StrongPass!234"
    assert verify_password("StrongPass!234", hashed)
    assert not verify_password("wrong", hashed)


def test_generated_cases_are_validated_and_duplicate_scenarios_removed():
    cases = validate_generated_cases(
        [valid_ai_case(), valid_ai_case("VALID LOGIN!!")],
        "8efbdbce-b063-44c9-94ab-4fc7f37993f3",
    )
    assert len(cases) == 1
    assert cases[0].requirement_id.hex == "8efbdbceb06344c994ab4fc7f37993f3"
    with pytest.raises(ValidationError):
        validate_generated_cases(
            [{**valid_ai_case(), "priority": "urgent"}], "8efbdbce-b063-44c9-94ab-4fc7f37993f3"
        )
    with pytest.raises(ValueError):
        validate_generated_cases([], "8efbdbce-b063-44c9-94ab-4fc7f37993f3")
    with pytest.raises(ValueError):
        validate_generated_cases(["not-a-case"], "8efbdbce-b063-44c9-94ab-4fc7f37993f3")


def test_ai_provider_fails_explicitly_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(AIProviderError, match="OPENAI_API_KEY"):
        asyncio.run(OpenAIProvider().generate("Generate cases"))


def test_prompt_includes_requirement_context():
    prompt = build_prompt(
        SimpleNamespace(
            requirement_key="AUTH-4",
            title="Sign in",
            description="A user can sign in",
            acceptance_criteria="Valid credentials open the dashboard",
        ),
        9,
    )
    assert "AUTH-4" in prompt
    assert "Requested count: 9" in prompt
    assert "Valid credentials open the dashboard" in prompt


def test_csv_and_text_documents_are_parsed():
    file = UploadFile(filename="requirements.txt", file=io.BytesIO(b"User can reset a password."))
    filename, content = asyncio.run(extract_document_text(file))
    assert filename == "requirements.txt"
    assert content == "User can reset a password."

    csv_file = UploadFile(filename="items.csv", file=io.BytesIO(b"key,title\nREQ-1,Login"))
    _, csv_text = asyncio.run(extract_document_text(csv_file))
    assert "REQ-1 | Login" in csv_text


def test_unsupported_document_type_is_rejected():
    file = UploadFile(filename="payload.exe", file=io.BytesIO(b"not supported"))
    with pytest.raises(Exception) as error:
        asyncio.run(extract_document_text(file))
    assert getattr(error.value, "status_code", None) == 415


def test_pdf_docx_and_xlsx_documents_are_parsed():
    pdf_buffer = io.BytesIO()
    pdf = Canvas(pdf_buffer)
    pdf.drawString(40, 750, "PDF requirement text")
    pdf.save()
    pdf_file = UploadFile(filename="requirements.pdf", file=io.BytesIO(pdf_buffer.getvalue()))
    _, pdf_text = asyncio.run(extract_document_text(pdf_file))
    assert "PDF requirement text" in pdf_text

    docx_buffer = io.BytesIO()
    document = Document()
    document.add_paragraph("DOCX acceptance criteria")
    document.save(docx_buffer)
    docx_file = UploadFile(filename="requirements.docx", file=io.BytesIO(docx_buffer.getvalue()))
    _, docx_text = asyncio.run(extract_document_text(docx_file))
    assert docx_text == "DOCX acceptance criteria"

    xlsx_buffer = io.BytesIO()
    workbook = Workbook()
    workbook.active.append(["Key", "Requirement"])
    workbook.active.append(["REQ-8", "Export results"])
    workbook.save(xlsx_buffer)
    xlsx_file = UploadFile(filename="requirements.xlsx", file=io.BytesIO(xlsx_buffer.getvalue()))
    _, xlsx_text = asyncio.run(extract_document_text(xlsx_file))
    assert "REQ-8 | Export results" in xlsx_text


def test_document_size_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(settings, "upload_max_bytes", 4)
    file = UploadFile(filename="requirements.txt", file=io.BytesIO(b"12345"))
    with pytest.raises(Exception) as error:
        asyncio.run(extract_document_text(file))
    assert getattr(error.value, "status_code", None) == 413


def sample_case():
    return CaseEntity(
        case_key="TC-ABC123",
        requirement_id="8efbdbce-b063-44c9-94ab-4fc7f37993f3",
        scenario="Valid login",
        preconditions="User exists",
        steps=["Open sign in", "Submit credentials"],
        expected_result="Dashboard appears",
        test_data={"email": "qa@example.test"},
        priority="P1",
        severity="medium",
        test_type="positive",
        automation_feasibility="high",
        tags=["auth"],
        status="draft",
    )


@pytest.mark.parametrize("file_format", ["csv", "xlsx", "pdf"])
def test_exports_produce_expected_file_signatures(file_format):
    content, media_type, filename = export_cases([sample_case()], file_format)
    assert filename.endswith(file_format)
    assert content
    if file_format == "csv":
        assert b"Test Case ID" in content
    elif file_format == "xlsx":
        sheet = load_workbook(io.BytesIO(content), read_only=False).active
        assert sheet.freeze_panes == "A2"
        assert sheet.auto_filter.ref is not None
    else:
        assert media_type == "application/pdf"
        assert content.startswith(b"%PDF")


def test_export_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unsupported export format"):
        export_cases([sample_case()], "json")
