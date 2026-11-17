import csv
import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.models.entities import TestCase

HEADERS = [
    "Test Case ID",
    "Requirement ID",
    "Test Scenario",
    "Preconditions",
    "Test Steps",
    "Expected Result",
    "Test Data",
    "Priority",
    "Severity",
    "Test Type",
    "Automation Feasibility",
    "Tags",
    "Status",
]


def row_for(case: TestCase) -> list[str]:
    return [
        case.case_key,
        str(case.requirement_id),
        case.scenario,
        case.preconditions,
        "\n".join(f"{index}. {step}" for index, step in enumerate(case.steps, 1)),
        case.expected_result,
        str(case.test_data),
        case.priority,
        case.severity,
        case.test_type,
        case.automation_feasibility,
        ", ".join(case.tags),
        case.status,
    ]


def export_cases(cases: list[TestCase], file_format: str) -> tuple[bytes, str, str]:
    rows = [row_for(case) for case in cases]
    if file_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "test-cases.csv"
    if file_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Test Cases"
        sheet.append(HEADERS)
        for row in rows:
            sheet.append(row)
        header_fill = PatternFill("solid", fgColor="173B57")
        for cell in sheet[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            max_length = min(max(len(str(cell.value or "")) for cell in column) + 2, 60)
            sheet.column_dimensions[get_column_letter(column[0].column)].width = max(14, max_length)
        buffer = io.BytesIO()
        workbook.save(buffer)
        return (
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "test-cases.xlsx",
        )
    if file_format == "pdf":
        output = io.BytesIO()
        document = SimpleDocTemplate(output, pagesize=landscape(letter), title="Test Cases")
        table_data: list[list[Any]] = [[header for header in HEADERS]]
        table_data.extend([[value[:500] for value in row] for row in rows])
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173B57")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        document.build([table])
        return output.getvalue(), "application/pdf", "test-cases.pdf"
    raise ValueError(f"Unsupported export format: {file_format}")
