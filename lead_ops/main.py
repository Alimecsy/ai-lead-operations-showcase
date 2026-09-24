from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .adapters import MockAdapterSuite
from .demo import run_demo_suite
from .models import AssessmentIntake, ChatIntake, DemoRequest, RetryResponse
from .store import LeadStore
from .workflow import FeatureFlags, WorkflowService


def create_app(
    *, store: LeadStore | None = None, service: WorkflowService | None = None
) -> FastAPI:
    resolved_store = store or LeadStore(os.getenv("SHOWCASE_DB_PATH", "data/lead_ops.sqlite3"))
    resolved_service = service or WorkflowService(
        resolved_store, MockAdapterSuite.create(), FeatureFlags.from_env()
    )
    app = FastAPI(
        title="AI Lead Operations Showcase",
        version="0.1.0",
        description="Synthetic, local-first demonstration of an AI-assisted lead workflow.",
    )
    origins = [origin.strip() for origin in os.getenv("SHOWCASE_ALLOWED_ORIGINS", "*").split(",")]
    operator_token = os.getenv("SHOWCASE_OPERATOR_TOKEN")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    def require_operator(request: Request) -> None:
        if operator_token and request.headers.get("x-operator-token") != operator_token:
            raise HTTPException(status_code=401, detail="Operator authentication required")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "feature_flags": resolved_service.flags.as_dict()}

    @app.post("/chat")
    def chat(payload: ChatIntake) -> dict[str, Any]:
        return resolved_service.chat(payload)

    @app.post("/assessment")
    def assessment(payload: AssessmentIntake) -> dict[str, Any]:
        return resolved_service.assessment(payload)

    @app.get("/leads/{lead_id}")
    def get_lead(lead_id: str, request: Request) -> dict[str, Any]:
        require_operator(request)
        try:
            return resolved_service.lead_view(lead_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Lead not found") from exc

    @app.post("/leads/{lead_id}/retry", response_model=RetryResponse)
    def retry(lead_id: str, request: Request) -> RetryResponse:
        require_operator(request)
        try:
            return RetryResponse(**resolved_service.retry(lead_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Lead not found") from exc

    @app.post("/demo/run")
    def demo(request: DemoRequest) -> dict[str, Any]:
        demo_service = WorkflowService(
            LeadStore(":memory:"),
            MockAdapterSuite.create(fail_once={"crm"} if request.inject_failure else set()),
            FeatureFlags(),
        )
        return run_demo_suite(demo_service)

    return app


app = create_app()
