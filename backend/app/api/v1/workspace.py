import csv
import io
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, require_project_access, require_roles
from app.application.ai_generation import (
    AIProviderError,
    OpenAIProvider,
    build_prompt,
    validate_generated_cases,
)
from app.application.document_parser import extract_document_text
from app.application.exports import export_cases
from app.config import settings
from app.db import get_db
from app.models.entities import (
    AIRequest,
    AuditLog,
    ExportRecord,
    Module,
    Notification,
    Project,
    ProjectMember,
    Release,
    Requirement,
    TestCase,
    User,
)
from app.schemas.contracts import (
    PageOfTestCases,
    ProjectCreate,
    ProjectRead,
    RequirementCreate,
    RequirementPatch,
    RequirementRead,
    TestCaseCreate,
    TestCasePatch,
    TestCaseRead,
    TestCaseReplace,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["workspace"])
cache = redis.Redis.from_url(
    settings.redis_url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2
)


def audit(
    db: Session,
    user: User,
    action: str,
    entity_type: str,
    entity_id: UUID,
    details: dict | None = None,
):
    db.add(
        AuditLog(
            actor_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
    )


def require_requirement(db: Session, requirement_id: UUID) -> Requirement:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requirement not found")
    return requirement


def make_case(db: Session, project_id: UUID, data: TestCaseCreate) -> TestCase:
    case = TestCase(
        project_id=project_id,
        requirement_id=data.requirement_id,
        case_key=f"TC-{uuid.uuid4().hex[:10].upper()}",
        **data.model_dump(exclude={"requirement_id"}),
    )
    db.add(case)
    return case


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Project).order_by(Project.created_at.desc())
    if user.role != "admin":
        query = query.where(
            or_(
                Project.created_by == user.id,
                Project.id.in_(
                    select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
                ),
            )
        )
    return list(db.scalars(query).all())


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    project = Project(
        name=data.name.strip(), description=data.description.strip(), created_by=user.id
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id))
    audit(db, user, "project.created", "project", project.id)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}/requirements", response_model=list[RequirementRead])
def list_requirements(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_project_access(project_id, db, user)
    return list(
        db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project_id)
            .order_by(Requirement.created_at.desc())
        ).all()
    )


@router.post(
    "/projects/{project_id}/requirements",
    response_model=RequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_requirement(
    project_id: UUID,
    data: RequirementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    require_project_access(project_id, db, user, write=True)
    duplicate = db.scalar(
        select(Requirement.id).where(
            Requirement.project_id == project_id,
            Requirement.requirement_key == data.requirement_key,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Requirement key already exists in this project"
        )
    requirement = Requirement(project_id=project_id, created_by=user.id, **data.model_dump())
    db.add(requirement)
    db.flush()
    audit(db, user, "requirement.created", "requirement", requirement.id)
    db.add(
        Notification(
            user_id=user.id,
            event="requirement.created",
            message=f"Requirement {requirement.requirement_key} created",
        )
    )
    db.commit()
    db.refresh(requirement)
    return requirement


@router.patch("/requirements/{requirement_id}", response_model=RequirementRead)
def update_requirement(
    requirement_id: UUID,
    data: RequirementPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    requirement = require_requirement(db, requirement_id)
    require_project_access(requirement.project_id, db, user, write=True)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one field must be provided"
        )
    if "requirement_key" in changes:
        duplicate = db.scalar(
            select(Requirement.id).where(
                Requirement.project_id == requirement.project_id,
                Requirement.requirement_key == changes["requirement_key"],
                Requirement.id != requirement.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Requirement key already exists in this project"
            )
    for key, value in changes.items():
        setattr(requirement, key, value)
    audit(
        db,
        user,
        "requirement.updated",
        "requirement",
        requirement.id,
        {"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(requirement)
    return requirement


@router.delete("/requirements/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requirement(
    requirement_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    requirement = require_requirement(db, requirement_id)
    require_project_access(requirement.project_id, db, user, write=True)
    audit(
        db,
        user,
        "requirement.deleted",
        "requirement",
        requirement.id,
        {"requirement_key": requirement.requirement_key},
    )
    db.delete(requirement)
    db.commit()


@router.post(
    "/projects/{project_id}/requirements/import",
    response_model=RequirementRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_requirement(
    project_id: UUID,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    require_project_access(project_id, db, user, write=True)
    filename, text = await extract_document_text(file)
    base = (
        re.sub(r"[^A-Za-z0-9]+", "-", filename.rsplit(".", 1)[0]).strip("-").upper()[:50]
        or "IMPORT"
    )
    key = f"{base}-{uuid.uuid4().hex[:6].upper()}"
    requirement = Requirement(
        project_id=project_id,
        requirement_key=key,
        title=filename.rsplit(".", 1)[0][:240],
        description=text,
        acceptance_criteria="",
        source_file=filename,
        created_by=user.id,
    )
    db.add(requirement)
    db.flush()
    audit(db, user, "requirement.imported", "requirement", requirement.id, {"filename": filename})
    db.commit()
    db.refresh(requirement)
    return requirement


@router.post("/projects/{project_id}/requirements/import-bulk", status_code=status.HTTP_201_CREATED)
async def import_requirements_csv(
    project_id: UUID,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    require_project_access(project_id, db, user, write=True)
    filename, text = await extract_document_text(file)
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Bulk import requires a CSV file"
        )
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    required = {"requirement_key", "title", "description"}
    if not reader.fieldnames or not required.issubset(
        {name.strip().lower() for name in reader.fieldnames}
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "CSV headers must include requirement_key, title, description",
        )
    parsed_rows = [
        {key.strip().lower(): value for key, value in row.items() if key} for row in reader
    ]
    keys = [(row.get("requirement_key") or "").strip() for row in parsed_rows]
    if len(keys) != len(set(keys)):
        raise HTTPException(status.HTTP_409_CONFLICT, "CSV contains duplicate requirement keys")
    existing_keys = (
        set(
            db.scalars(
                select(Requirement.requirement_key).where(
                    Requirement.project_id == project_id,
                    Requirement.requirement_key.in_(keys),
                )
            ).all()
        )
        if keys
        else set()
    )
    if existing_keys:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Requirement keys already exist: {', '.join(sorted(existing_keys))}",
        )
    created = []
    for row in parsed_rows:
        normalized = {
            key.strip().lower(): (value or "").strip() for key, value in row.items() if key
        }
        if (
            not normalized.get("requirement_key")
            or not normalized.get("title")
            or not normalized.get("description")
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Each CSV row requires a key, title, and description",
            )
        requirement = Requirement(
            project_id=project_id,
            requirement_key=normalized["requirement_key"][:80],
            title=normalized["title"][:240],
            description=normalized["description"][:20000],
            acceptance_criteria=normalized.get("acceptance_criteria", "")[:20000],
            source_file=filename,
            created_by=user.id,
        )
        db.add(requirement)
        db.flush()
        created.append(requirement)
    for requirement in created:
        audit(
            db, user, "requirement.imported", "requirement", requirement.id, {"filename": filename}
        )
    db.commit()
    return {
        "imported": len(created),
        "requirements": [RequirementRead.model_validate(item) for item in created],
    }


@router.post("/requirements/{requirement_id}/generate", response_model=list[TestCaseRead])
async def generate_test_cases(
    requirement_id: UUID,
    count: int = Query(default=12, ge=1, le=40),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    requirement = require_requirement(db, requirement_id)
    require_project_access(requirement.project_id, db, user, write=True)
    provider = OpenAIProvider()
    ai_record = AIRequest(
        user_id=user.id,
        requirement_id=requirement.id,
        provider=provider.name,
        model=settings.openai_model,
        status="pending",
    )
    db.add(ai_record)
    db.flush()
    try:
        model, raw_cases = await provider.generate(build_prompt(requirement, count))
        cases = validate_generated_cases(raw_cases[:count], requirement.id)
    except AIProviderError as exc:
        ai_record.status = "failed"
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except (ValidationError, ValueError) as exc:
        ai_record.status = "failed"
        db.commit()
        logger.warning("AI test case response failed schema validation", extra={"error": str(exc)})
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "AI provider returned test cases that failed validation"
        ) from exc
    existing_scenarios = {
        re.sub(r"\W+", " ", scenario.casefold()).strip()
        for scenario in db.scalars(
            select(TestCase.scenario).where(TestCase.requirement_id == requirement.id)
        )
    }
    cases = [
        case
        for case in cases
        if re.sub(r"\W+", " ", case.scenario.casefold()).strip() not in existing_scenarios
    ]
    if not cases:
        ai_record.status = "completed"
        ai_record.model = model
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Generation produced no new scenarios; update the requirement before regenerating",
        )
    ai_record.model = model
    ai_record.status = "completed"
    created = [make_case(db, requirement.project_id, case) for case in cases]
    audit(db, user, "test_cases.generated", "requirement", requirement.id, {"count": len(created)})
    db.add(
        Notification(
            user_id=user.id,
            event="generation.completed",
            message=f"Generated {len(created)} test cases",
        )
    )
    db.commit()
    for case in created:
        db.refresh(case)
    return created


@router.get("/projects/{project_id}/test-cases", response_model=PageOfTestCases)
def list_test_cases(
    project_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    priority: str | None = Query(default=None, pattern="^P[012]$"),
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    requirement_id: UUID | None = None,
    module: str | None = Query(default=None, max_length=120),
    sprint: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_project_access(project_id, db, user)
    query = select(TestCase).where(TestCase.project_id == project_id)
    if priority:
        query = query.where(TestCase.priority == priority)
    if status_filter:
        query = query.where(TestCase.status == status_filter)
    if requirement_id:
        query = query.where(TestCase.requirement_id == requirement_id)
    if module:
        query = query.where(TestCase.module == module)
    if sprint:
        query = query.where(TestCase.sprint == sprint)
    if q:
        query = query.where(
            or_(
                TestCase.scenario.ilike(f"%{q}%"),
                TestCase.case_key.ilike(f"%{q}%"),
                TestCase.preconditions.ilike(f"%{q}%"),
                TestCase.expected_result.ilike(f"%{q}%"),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        db.scalars(
            query.order_by(TestCase.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return PageOfTestCases(items=items, total=total, page=page, page_size=page_size)


@router.post(
    "/projects/{project_id}/test-cases",
    response_model=TestCaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_test_case(
    project_id: UUID,
    data: TestCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    require_project_access(project_id, db, user, write=True)
    requirement = require_requirement(db, data.requirement_id)
    if requirement.project_id != project_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Requirement is not part of this project"
        )
    case = make_case(db, project_id, data)
    db.flush()
    audit(db, user, "test_case.created", "test_case", case.id)
    db.commit()
    db.refresh(case)
    return case


@router.get("/test-cases/{case_id}", response_model=TestCaseRead)
def get_test_case(case_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test case not found")
    require_project_access(case.project_id, db, user)
    return case


@router.patch("/test-cases/{case_id}", response_model=TestCaseRead)
def update_test_case(
    case_id: UUID,
    data: TestCasePatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test case not found")
    require_project_access(case.project_id, db, user, write=True)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one field must be provided"
        )
    if changes.get("status") == "approved" and user.role not in {"admin", "qa_lead"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only QA Leads and Admins can approve test cases"
        )
    for key, value in changes.items():
        setattr(case, key, value)
    case.version += 1
    case.updated_at = datetime.now(UTC)
    audit(db, user, "test_case.updated", "test_case", case.id, {"fields": sorted(changes)})
    db.commit()
    db.refresh(case)
    return case


@router.put("/test-cases/{case_id}", response_model=TestCaseRead)
def replace_test_case(
    case_id: UUID,
    data: TestCaseReplace,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test case not found")
    require_project_access(case.project_id, db, user, write=True)
    requirement = require_requirement(db, data.requirement_id)
    if requirement.project_id != case.project_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Requirement is not part of this project"
        )
    if data.status == "approved" and user.role not in {"admin", "qa_lead"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only QA Leads and Admins can approve test cases"
        )
    for key, value in data.model_dump(exclude={"requirement_id"}).items():
        setattr(case, key, value)
    case.requirement_id = data.requirement_id
    case.version += 1
    case.updated_at = datetime.now(UTC)
    audit(db, user, "test_case.replaced", "test_case", case.id, {"version": case.version})
    db.commit()
    db.refresh(case)
    return case


@router.delete("/test-cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test case not found")
    require_project_access(case.project_id, db, user, write=True)
    audit(db, user, "test_case.deleted", "test_case", case.id, {"case_key": case.case_key})
    db.delete(case)
    db.commit()


@router.get("/test-cases/{case_id}/history")
def test_case_history(
    case_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test case not found")
    require_project_access(case.project_id, db, user)
    logs = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "test_case", AuditLog.entity_id == case_id)
        .order_by(AuditLog.created_at.desc())
    )
    return [
        {"action": row.action, "details": row.details, "created_at": row.created_at} for row in logs
    ]


@router.get("/projects/{project_id}/dashboard")
def dashboard(project_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_project_access(project_id, db, user)
    cache_key = f"dashboard:{project_id}"
    try:
        cached = cache.get(cache_key)
        if cached:
            return json.loads(cached)
    except redis.RedisError as exc:
        logger.warning("Dashboard cache unavailable", extra={"error": str(exc)})
    requirements = (
        db.scalar(select(func.count(Requirement.id)).where(Requirement.project_id == project_id))
        or 0
    )
    cases = list(db.scalars(select(TestCase).where(TestCase.project_id == project_id)).all())
    covered = len({case.requirement_id for case in cases})
    total = len(cases)
    counts = {
        priority: sum(case.priority == priority for case in cases)
        for priority in ("P0", "P1", "P2")
    }
    normalized = [re.sub(r"\W+", " ", case.scenario.casefold()).strip() for case in cases]
    duplicate_count = len(normalized) - len(set(normalized))
    result = {
        "total_requirements": requirements,
        "total_test_cases": total,
        "coverage_percent": round(covered / requirements * 100, 1) if requirements else 0,
        "covered_requirements": covered,
        "duplicate_test_cases": duplicate_count,
        "automation_readiness_percent": round(
            sum(case.automation_feasibility == "high" for case in cases) / total * 100, 1
        )
        if total
        else 0,
        "priority_distribution": counts,
        "defect_prediction_score": round(
            min(100, (counts["P0"] * 20 + counts["P1"] * 10 + counts["P2"] * 3) / max(total, 1)), 1
        ),
    }
    try:
        cache.setex(cache_key, 30, json.dumps(result))
    except redis.RedisError as exc:
        logger.warning("Dashboard cache write failed", extra={"error": str(exc)})
    return result


@router.get("/projects/{project_id}/exports/{file_format}")
def export_project(
    project_id: UUID,
    file_format: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_project_access(project_id, db, user)
    if file_format not in {"csv", "xlsx", "pdf"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export format must be csv, xlsx, or pdf")
    cases = list(
        db.scalars(
            select(TestCase).where(TestCase.project_id == project_id).order_by(TestCase.created_at)
        ).all()
    )
    content, media_type, filename = export_cases(cases, file_format)
    db.add(ExportRecord(project_id=project_id, user_id=user.id, format=file_format))
    audit(db, user, "export.created", "project", project_id, {"format": file_format})
    db.commit()
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/projects/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def assign_project_member(
    project_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead")),
):
    require_project_access(project_id, db, user, write=True)
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if db.get(ProjectMember, (project_id, user_id)) is None:
        db.add(ProjectMember(project_id=project_id, user_id=user_id))
        audit(db, user, "project.member_assigned", "project", project_id, {"user_id": str(user_id)})
        db.commit()


@router.post("/projects/{project_id}/releases", status_code=status.HTTP_201_CREATED)
def create_release(
    project_id: UUID,
    name: str = Query(min_length=1, max_length=120),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    require_project_access(project_id, db, user, write=True)
    release = Release(project_id=project_id, name=name.strip())
    db.add(release)
    db.commit()
    db.refresh(release)
    return {"id": release.id, "project_id": release.project_id, "name": release.name}


@router.post("/projects/{project_id}/modules", status_code=status.HTTP_201_CREATED)
def create_module(
    project_id: UUID,
    name: str = Query(min_length=1, max_length=120),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "qa_lead", "qa_engineer")),
):
    require_project_access(project_id, db, user, write=True)
    module = Module(project_id=project_id, name=name.strip())
    db.add(module)
    db.commit()
    db.refresh(module)
    return {"id": module.id, "project_id": module.project_id, "name": module.name}


@router.get("/notifications")
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": row.id,
            "event": row.event,
            "message": row.message,
            "read_at": row.read_at,
            "created_at": row.created_at,
        }
        for row in rows
    ]
