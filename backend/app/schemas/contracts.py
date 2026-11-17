from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["admin", "qa_lead", "qa_engineer", "read_only"]
TestType = Literal[
    "positive",
    "negative",
    "boundary",
    "edge",
    "security",
    "api",
    "accessibility",
    "performance",
    "functional",
    "regression",
    "smoke",
    "uat",
]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    csrf_token: str


class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: Role
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)


class ProjectRead(ProjectCreate):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RequirementCreate(BaseModel):
    requirement_key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=20000)
    acceptance_criteria: str = Field(default="", max_length=20000)


class RequirementRead(RequirementCreate):
    id: UUID
    project_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RequirementPatch(BaseModel):
    requirement_key: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    acceptance_criteria: str | None = Field(default=None, max_length=20000)


class TestCaseCreate(BaseModel):
    requirement_id: UUID
    scenario: str = Field(min_length=1, max_length=500)
    preconditions: str = Field(default="", max_length=10000)
    steps: list[str] = Field(min_length=1, max_length=50)
    expected_result: str = Field(min_length=1, max_length=10000)
    test_data: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["P0", "P1", "P2"]
    severity: Literal["critical", "high", "medium", "low"]
    test_type: TestType
    automation_feasibility: Literal["high", "medium", "low"]
    tags: list[str] = Field(default_factory=list, max_length=20)
    module: str | None = Field(default=None, max_length=120)
    sprint: str | None = Field(default=None, max_length=80)

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: list[str]) -> list[str]:
        if any(not step.strip() or len(step) > 2000 for step in steps):
            raise ValueError("Each step must contain 1-2000 characters")
        return steps


class TestCasePatch(BaseModel):
    scenario: str | None = Field(default=None, min_length=1, max_length=500)
    preconditions: str | None = Field(default=None, max_length=10000)
    steps: list[str] | None = Field(default=None, min_length=1, max_length=50)
    expected_result: str | None = Field(default=None, min_length=1, max_length=10000)
    test_data: dict[str, Any] | None = None
    priority: Literal["P0", "P1", "P2"] | None = None
    severity: Literal["critical", "high", "medium", "low"] | None = None
    test_type: TestType | None = None
    automation_feasibility: Literal["high", "medium", "low"] | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    status: Literal["draft", "ready", "approved", "deprecated"] | None = None
    module: str | None = Field(default=None, max_length=120)
    sprint: str | None = Field(default=None, max_length=80)

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: list[str] | None) -> list[str] | None:
        if steps is not None and any(not step.strip() or len(step) > 2000 for step in steps):
            raise ValueError("Each step must contain 1-2000 characters")
        return steps


class TestCaseReplace(TestCaseCreate):
    status: Literal["draft", "ready", "approved", "deprecated"] = "draft"


class TestCaseRead(BaseModel):
    id: UUID
    case_key: str
    requirement_id: UUID
    scenario: str
    preconditions: str
    steps: list[str]
    expected_result: str
    test_data: dict[str, Any]
    priority: str
    severity: str
    test_type: str
    automation_feasibility: str
    tags: list[str]
    status: str
    module: str | None
    sprint: str | None
    version: int
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PageOfTestCases(BaseModel):
    items: list[TestCaseRead]
    total: int
    page: int
    page_size: int
