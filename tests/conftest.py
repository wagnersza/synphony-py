from datetime import UTC, datetime

import pytest

from synphony.models import Issue


@pytest.fixture
def make_issue() -> Issue:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    return Issue(
        id="10001",
        identifier="DEMO-1",
        title="Add tests",
        state="Ready",
        created_at=now,
        updated_at=now,
    )
