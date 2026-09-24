from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4


class AdapterError(RuntimeError):
    """A downstream adapter failed after local state was recorded."""


class Adapter(Protocol):
    name: str

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class MockAdapter:
    name: str
    fail_once: set[str] = field(default_factory=set)
    records: list[dict[str, Any]] = field(default_factory=list)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.name in self.fail_once:
            self.fail_once.remove(self.name)
            raise AdapterError(f"mock failure injected for {self.name}")
        record = {"external_id": f"mock-{self.name}-{uuid4().hex[:8]}", **payload}
        self.records.append(record)
        return record


@dataclass
class MockAdapterSuite:
    crm: MockAdapter
    booking: MockAdapter
    follow_up: MockAdapter
    human_review: MockAdapter

    @classmethod
    def create(cls, *, fail_once: set[str] | None = None) -> MockAdapterSuite:
        failures = fail_once or set()
        return cls(
            crm=MockAdapter("crm", failures),
            booking=MockAdapter("booking", failures),
            follow_up=MockAdapter("follow_up", failures),
            human_review=MockAdapter("human_review", failures),
        )

    def for_name(self, name: str) -> MockAdapter:
        adapters = {
            "crm": self.crm,
            "booking": self.booking,
            "follow_up": self.follow_up,
            "human_review": self.human_review,
        }
        try:
            return adapters[name]
        except KeyError as exc:
            raise ValueError(f"Unknown adapter: {name}") from exc
