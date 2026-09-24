from collections.abc import Iterator

import pytest

from lead_ops.adapters import MockAdapterSuite
from lead_ops.store import LeadStore
from lead_ops.workflow import FeatureFlags, WorkflowService


@pytest.fixture
def service() -> Iterator[WorkflowService]:
    store = LeadStore(":memory:")
    yield WorkflowService(store, MockAdapterSuite.create(), FeatureFlags())
    store.close()
