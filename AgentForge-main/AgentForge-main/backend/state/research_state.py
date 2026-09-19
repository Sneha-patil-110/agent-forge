from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchState(BaseModel):
    documentation: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Technology name -> fetched Context7 documentation excerpt. "
            "Populated once per workflow run (DocumentationPrefetchService), "
            "before Developer, and reused by every agent for the rest of the "
            "run instead of each one deciding on its own whether to look it up."
        ),
    )
