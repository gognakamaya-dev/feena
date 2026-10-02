"""Explicit multi-service scenarios; generated tests carry the same assertions."""
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .simulation_config import StrictModel, local_path


class IntegrationStep(StrictModel):
    service: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: str
    json_body: dict[str, Any] | None = None
    expected_status: int = Field(default=200, ge=200, le=599)
    expected_json: dict[str, Any] = Field(min_length=1)
    poll_seconds: float = Field(default=0, ge=0, le=10)

    _path = field_validator("path")(local_path)

    @model_validator(mode="after")
    def read_only_poll(self):
        if self.poll_seconds and self.method != "GET":
            raise ValueError("Only GET assertions may be polled; write explicit retry steps for mutations")
        return self


class IntegrationScenario(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    goal: str = Field(min_length=1)
    setup: list[IntegrationStep] = Field(default_factory=list, max_length=20)
    steps: list[IntegrationStep] = Field(min_length=1, max_length=50)
    cleanup: list[IntegrationStep] = Field(default_factory=list, max_length=20)

    @property
    def services(self):
        return sorted({s.service for s in self.setup + self.steps + self.cleanup})
