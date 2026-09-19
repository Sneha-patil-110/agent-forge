from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models.generated_project import GeneratedProjectRecord


class GeneratedProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        run_id: str,
        project_name: str | None,
        project_description: str | None,
        objective: str | None,
        status: str,
        backend_tech: str | None,
        frontend_tech: str | None,
        database_tech: str | None,
        deployment_tech: str | None,
        requirements: list[str],
        tech_stack: list[str],
        output_directory: str | None,
    ) -> GeneratedProjectRecord:
        record = self.session.get(GeneratedProjectRecord, run_id)

        if record is None:
            record = GeneratedProjectRecord(run_id=run_id)
            self.session.add(record)

        record.project_name = project_name
        record.project_description = project_description
        record.objective = objective
        record.status = status
        record.backend_tech = backend_tech
        record.frontend_tech = frontend_tech
        record.database_tech = database_tech
        record.deployment_tech = deployment_tech
        record.requirements = requirements
        record.tech_stack = tech_stack
        record.output_directory = output_directory

        self.session.flush()

        return record

    def get(self, run_id: str) -> GeneratedProjectRecord | None:
        return self.session.get(GeneratedProjectRecord, run_id)
