from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.repositories.event_repository import EventRepository
from backend.repositories.generated_project_repository import GeneratedProjectRepository
from backend.repositories.knowledge_repository import KnowledgeRepository
from backend.repositories.project_repository import ProjectRepository
from backend.repositories.run_repository import RunRepository
from backend.repositories.user_repository import UserRepository


def _now():
    return datetime.now(UTC)


def test_run_repository_upsert_creates_then_updates(db_session) -> None:
    repository = RunRepository(db_session)
    now = _now()

    repository.upsert(
        run_id="af_20260717_aaaaaaaa",
        status="running",
        current_step="Executing analysis agent",
        current_agent="analysis",
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
        user_id=None,
    )
    db_session.commit()

    record = repository.get("af_20260717_aaaaaaaa")
    assert record.status == "running"

    later = _now()
    repository.upsert(
        run_id="af_20260717_aaaaaaaa",
        status="completed",
        current_step="Completed documentation agent",
        current_agent="documentation",
        error_message=None,
        test_retry_count=0,
        review_retry_count=1,
        created_at=now,
        updated_at=later,
        started_at=now,
        completed_at=later,
        user_id=None,
    )
    db_session.commit()

    updated = repository.get("af_20260717_aaaaaaaa")
    assert updated.status == "completed"
    assert updated.review_retry_count == 1
    assert updated.completed_at is not None


def test_run_repository_list_filters_by_status(db_session) -> None:
    repository = RunRepository(db_session)
    now = _now()

    for run_id, status in (
        ("af_20260717_bbbbbbbb", "running"),
        ("af_20260717_cccccccc", "completed"),
        ("af_20260717_dddddddd", "failed"),
    ):
        repository.upsert(
            run_id=run_id,
            status=status,
            current_step=None,
            current_agent=None,
            error_message=None,
            test_retry_count=0,
            review_retry_count=0,
            created_at=now,
            updated_at=now,
            started_at=now,
            completed_at=None,
            user_id=None,
        )
    db_session.commit()

    completed = repository.list(status=["completed"])
    assert [record.run_id for record in completed] == ["af_20260717_cccccccc"]

    all_runs = repository.list()
    assert len(all_runs) == 3


def test_run_repository_resumable_pseudo_status_and_count(db_session) -> None:
    repository = RunRepository(db_session)
    now = _now()

    for run_id, status in (
        ("af_20260719_r0000001", "initialized"),
        ("af_20260719_r0000002", "running"),
        ("af_20260719_r0000003", "waiting_for_user"),
        ("af_20260719_r0000004", "completed"),
        ("af_20260719_r0000005", "failed"),
    ):
        repository.upsert(
            run_id=run_id,
            status=status,
            current_step=None,
            current_agent=None,
            error_message=None,
            test_retry_count=0,
            review_retry_count=0,
            created_at=now,
            updated_at=now,
            started_at=now,
            completed_at=None,
            user_id=None,
        )
    db_session.commit()

    resumable = repository.list(status=["resumable"])
    assert {record.run_id for record in resumable} == {
        "af_20260719_r0000001",
        "af_20260719_r0000002",
        "af_20260719_r0000003",
    }
    assert repository.count(status=["resumable"]) == 3
    assert repository.count() == 5

    with pytest.raises(Exception):
        repository.list(status=["cancelled"])


def test_run_repository_search_matches_run_id_agent_or_request_text(db_session) -> None:
    repository = RunRepository(db_session)
    now = _now()

    repository.upsert(
        run_id="af_20260719_search01",
        status="running",
        current_step=None,
        current_agent="developer",
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
        user_id=None,
        request_text="Add authentication to the expense tracker",
    )
    repository.upsert(
        run_id="af_20260719_search02",
        status="running",
        current_step=None,
        current_agent="tester",
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
        user_id=None,
        request_text="Build a calculator",
    )
    db_session.commit()

    by_prompt = repository.list(q="authentication")
    assert [r.run_id for r in by_prompt] == ["af_20260719_search01"]

    by_run_id = repository.list(q="search02")
    assert [r.run_id for r in by_run_id] == ["af_20260719_search02"]


def test_run_repository_sort_newest_oldest_and_status(db_session) -> None:
    repository = RunRepository(db_session)
    early = datetime(2026, 1, 1, tzinfo=UTC)
    late = datetime(2026, 6, 1, tzinfo=UTC)

    repository.upsert(
        run_id="af_20260719_sort0001",
        status="completed",
        current_step=None,
        current_agent=None,
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=early,
        updated_at=early,
        started_at=early,
        completed_at=None,
        user_id=None,
    )
    repository.upsert(
        run_id="af_20260719_sort0002",
        status="running",
        current_step=None,
        current_agent=None,
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=late,
        updated_at=late,
        started_at=late,
        completed_at=None,
        user_id=None,
    )
    db_session.commit()

    newest_first = repository.list(sort="newest")
    assert [r.run_id for r in newest_first] == ["af_20260719_sort0002", "af_20260719_sort0001"]

    oldest_first = repository.list(sort="oldest")
    assert [r.run_id for r in oldest_first] == ["af_20260719_sort0001", "af_20260719_sort0002"]

    by_status = repository.list(sort="status")
    assert by_status[0].run_id == "af_20260719_sort0002"


def test_event_repository_add_and_list_for_run(db_session) -> None:
    RunRepository(db_session).upsert(
        run_id="af_20260717_eeeeeeee",
        status="running",
        current_step=None,
        current_agent=None,
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=_now(),
        updated_at=_now(),
        started_at=_now(),
        completed_at=None,
        user_id=None,
    )
    db_session.commit()

    repository = EventRepository(db_session)
    repository.add(
        run_id="af_20260717_eeeeeeee",
        event_type="workflow_started",
        agent=None,
        message=None,
        event_metadata={},
        timestamp=_now(),
    )
    repository.add(
        run_id="af_20260717_eeeeeeee",
        event_type="agent_started",
        agent="analysis",
        message="Analysis started",
        event_metadata={"foo": "bar"},
        timestamp=_now(),
    )
    db_session.commit()

    events = repository.list_for_run("af_20260717_eeeeeeee")
    assert [record.event_type for record in events] == ["workflow_started", "agent_started"]
    assert events[1].event_metadata == {"foo": "bar"}


def test_generated_project_repository_upsert_and_get(db_session) -> None:
    RunRepository(db_session).upsert(
        run_id="af_20260717_ffffffff",
        status="running",
        current_step=None,
        current_agent=None,
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=_now(),
        updated_at=_now(),
        started_at=_now(),
        completed_at=None,
        user_id=None,
    )
    db_session.commit()

    repository = GeneratedProjectRepository(db_session)
    repository.upsert(
        run_id="af_20260717_ffffffff",
        project_name="Expense Tracker",
        project_description="A FastAPI expense tracker.",
        objective="Track expenses",
        status="analyzed",
        backend_tech="FastAPI",
        frontend_tech=None,
        database_tech="SQLite",
        deployment_tech=None,
        requirements=["auth", "reporting"],
        tech_stack=["FastAPI", "SQLite"],
        output_directory="/tmp/workspace/af_20260717_ffffffff",
    )
    db_session.commit()

    record = repository.get("af_20260717_ffffffff")
    assert record.project_name == "Expense Tracker"
    assert record.requirements == ["auth", "reporting"]


def test_knowledge_repository_upsert_and_filter(db_session) -> None:
    RunRepository(db_session).upsert(
        run_id="af_20260717_11111111",
        status="running",
        current_step=None,
        current_agent=None,
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=_now(),
        updated_at=_now(),
        started_at=_now(),
        completed_at=None,
        user_id=None,
    )
    db_session.commit()

    repository = KnowledgeRepository(db_session)
    now = _now()

    repository.upsert(
        run_id="af_20260717_11111111",
        entry_id="AD1",
        category="architecture_decision",
        title="Use repository pattern",
        content="Use the repository pattern for data access.",
        created_by="architect",
        status="active",
        source_id="AD1",
        supersedes=None,
        created_at=now,
        updated_at=now,
    )
    repository.upsert(
        run_id="af_20260717_11111111",
        entry_id="CS1",
        category="coding_standard",
        title="Use snake_case",
        content="Use snake_case for functions.",
        created_by="reviewer",
        status="active",
        source_id=None,
        supersedes=None,
        created_at=now,
        updated_at=now,
    )
    db_session.commit()

    all_entries = repository.list_for_run("af_20260717_11111111")
    assert len(all_entries) == 2

    architecture_only = repository.list_for_run("af_20260717_11111111", category="architecture_decision")
    assert [entry.id for entry in architecture_only] == ["AD1"]


def test_knowledge_repository_ids_are_scoped_per_run(db_session) -> None:
    for run_id in ("af_20260717_22222222", "af_20260717_33333333"):
        RunRepository(db_session).upsert(
            run_id=run_id,
            status="running",
            current_step=None,
            current_agent=None,
            error_message=None,
            test_retry_count=0,
            review_retry_count=0,
            created_at=_now(),
            updated_at=_now(),
            started_at=_now(),
            completed_at=None,
            user_id=None,
        )
    db_session.commit()

    repository = KnowledgeRepository(db_session)
    now = _now()

    for run_id in ("af_20260717_22222222", "af_20260717_33333333"):
        repository.upsert(
            run_id=run_id,
            entry_id="AD1",
            category="architecture_decision",
            title="Decision",
            content="Some decision.",
            created_by="architect",
            status="active",
            source_id="AD1",
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
    db_session.commit()

    assert len(repository.list_for_run("af_20260717_22222222")) == 1
    assert len(repository.list_for_run("af_20260717_33333333")) == 1


def test_user_repository_create_and_lookup(db_session) -> None:
    repository = UserRepository(db_session)
    user = repository.create(email="ada@example.com", hashed_password="hashed")
    db_session.commit()

    assert repository.get_by_email("ada@example.com").id == user.id
    assert repository.get_by_id(user.id).email == "ada@example.com"
    assert repository.get_by_email("nonexistent@example.com") is None


def _make_run(db_session, run_id: str, *, status: str = "running") -> None:
    RunRepository(db_session).upsert(
        run_id=run_id,
        status=status,
        current_step=None,
        current_agent=None,
        error_message=None,
        test_retry_count=0,
        review_retry_count=0,
        created_at=_now(),
        updated_at=_now(),
        started_at=_now(),
        completed_at=None,
        user_id=None,
    )


def test_project_repository_create_get_attach_run(db_session) -> None:
    user = UserRepository(db_session).create(
        email="grace@example.com", hashed_password="hashed"
    )
    _make_run(db_session, "af_20260719_aaaaaaaa")
    db_session.commit()

    repository = ProjectRepository(db_session)
    project = repository.create(
        id="proj_20260719_aaaaaaaa",
        user_id=user.id,
        name="Expense Tracker",
        initial_prompt="Build a fastapi expense tracker",
    )
    db_session.commit()

    fetched = repository.get(project.id)
    assert fetched is not None
    assert fetched.name == "Expense Tracker"
    assert fetched.run_count == 0
    assert fetched.latest_run_id is None

    repository.attach_run(project.id, "af_20260719_aaaaaaaa")
    db_session.commit()

    fetched = repository.get(project.id)
    assert fetched.latest_run_id == "af_20260719_aaaaaaaa"
    assert fetched.run_count == 1

    repository.attach_run(project.id, "af_20260719_aaaaaaaa")
    db_session.commit()
    assert repository.get(project.id).run_count == 1


def test_project_repository_get_owned_enforces_ownership(db_session) -> None:
    owner = UserRepository(db_session).create(
        email="owner@example.com", hashed_password="hashed"
    )
    stranger = UserRepository(db_session).create(
        email="stranger@example.com", hashed_password="hashed"
    )
    repository = ProjectRepository(db_session)
    project = repository.create(id="proj_20260719_bbbbbbbb", user_id=owner.id, name=None, initial_prompt=None)
    db_session.commit()

    assert repository.get_owned(project.id, owner.id) is not None
    assert repository.get_owned(project.id, stranger.id) is None
    assert repository.get_owned("proj_20260719_ffffffff", owner.id) is None


def test_project_repository_rename_and_soft_delete(db_session) -> None:
    user = UserRepository(db_session).create(email="mo@example.com", hashed_password="hashed")
    repository = ProjectRepository(db_session)
    project = repository.create(id="proj_20260719_cccccccc", user_id=user.id, name="Old name", initial_prompt=None)
    db_session.commit()

    repository.rename(project.id, "New name")
    db_session.commit()
    assert repository.get(project.id).name == "New name"

    repository.soft_delete(project.id)
    db_session.commit()
    assert repository.get(project.id).deleted_at is not None
    assert repository.get_owned(project.id, user.id) is None


def test_project_repository_list_filters_search_and_sorts(db_session) -> None:
    user = UserRepository(db_session).create(email="lin@example.com", hashed_password="hashed")
    other = UserRepository(db_session).create(email="kai@example.com", hashed_password="hashed")
    repository = ProjectRepository(db_session)

    repository.create(id="proj_20260719_r0000001", user_id=user.id, name="Running one", initial_prompt="alpha")
    repository.create(id="proj_20260719_r0000002", user_id=user.id, name="Failed one", initial_prompt="beta")
    repository.create(id="proj_20260719_r0000003", user_id=user.id, name="Completed one", initial_prompt="gamma")
    repository.create(id="proj_20260719_r0000004", user_id=other.id, name="Someone else's", initial_prompt="delta")
    db_session.commit()

    repository.update_status("proj_20260719_r0000001", "running")
    repository.update_status("proj_20260719_r0000002", "failed")
    repository.update_status("proj_20260719_r0000003", "completed")
    db_session.commit()

    mine = repository.list(user_id=user.id)
    assert {p.id for p in mine} == {
        "proj_20260719_r0000001",
        "proj_20260719_r0000002",
        "proj_20260719_r0000003",
    }
    assert repository.count(user_id=user.id) == 3

    resumable = repository.list(user_id=user.id, status=["resumable"])
    assert {p.id for p in resumable} == {"proj_20260719_r0000001"}

    by_prompt = repository.list(user_id=user.id, q="beta")
    assert {p.id for p in by_prompt} == {"proj_20260719_r0000002"}

    by_name = repository.list(user_id=user.id, q="Completed")
    assert {p.id for p in by_name} == {"proj_20260719_r0000003"}

    ordered = repository.list(user_id=user.id, sort="status")
    assert [p.id for p in ordered] == [
        "proj_20260719_r0000001",
        "proj_20260719_r0000002",
        "proj_20260719_r0000003",
    ]

    with pytest.raises(Exception):
        repository.list(user_id=user.id, status=["cancelled"])