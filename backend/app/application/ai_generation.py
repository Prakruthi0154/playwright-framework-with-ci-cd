import json
import re
from typing import Any

import httpx

from app.config import settings
from app.schemas.contracts import TestCaseCreate

GENERATION_PROMPT = """You are an experienced enterprise QA engineer. Create a balanced, requirement-traceable test suite.
Return only a JSON object with a "test_cases" array. Each case must have: scenario, preconditions,
steps (array of concise actionable strings), expected_result, test_data (object), priority (P0/P1/P2),
severity (critical/high/medium/low), test_type (positive, negative, boundary, edge, security, api,
accessibility, performance, functional, regression, smoke, uat), automation_feasibility (high/medium/low),
and tags (array of strings). Include positive, negative, boundary, error-handling, security,
accessibility and performance scenarios where applicable. Do not invent unspecified business rules;
mark assumptions explicitly in preconditions. Make expected results observable and steps reproducible.
Avoid duplicate scenarios. Do not output markdown or any text outside JSON.
Requirement key: {requirement_key}
Title: {title}
Description: {description}
Acceptance criteria: {acceptance_criteria}
Requested count: {count}"""


class AIProviderError(RuntimeError):
    pass


class TestGenerationProvider:
    name = "base"

    async def generate(self, prompt: str) -> tuple[str, list[dict[str, Any]]]:
        raise NotImplementedError


class OpenAIProvider(TestGenerationProvider):
    name = "openai"

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.base_url = settings.openai_base_url.rstrip("/")

    async def generate(self, prompt: str) -> tuple[str, list[dict[str, Any]]]:
        if not self.api_key:
            raise AIProviderError("AI generation is unavailable: OPENAI_API_KEY is not configured")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {
                                "role": "system",
                                "content": "You generate precise, realistic software test cases.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            payload = json.loads(content)
            cases = payload.get("test_cases")
            if not isinstance(cases, list) or not cases:
                raise AIProviderError("AI provider returned no test cases")
            return self.model, cases
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AIProviderError("AI provider request failed or returned invalid JSON") from exc


def build_prompt(requirement: Any, count: int) -> str:
    return GENERATION_PROMPT.format(
        requirement_key=requirement.requirement_key,
        title=requirement.title,
        description=requirement.description,
        acceptance_criteria=requirement.acceptance_criteria or "(not provided)",
        count=count,
    )


def validate_generated_cases(
    raw_cases: list[dict[str, Any]], requirement_id: Any
) -> list[TestCaseCreate]:
    validated: list[TestCaseCreate] = []
    seen: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("AI provider returned a test case with an invalid shape")
        data = dict(raw)
        data["requirement_id"] = requirement_id
        case = TestCaseCreate.model_validate(data)
        normalized = re.sub(r"\W+", " ", case.scenario.casefold()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        validated.append(case)
    if not validated:
        raise ValueError("AI provider returned no unique valid test cases")
    return validated
