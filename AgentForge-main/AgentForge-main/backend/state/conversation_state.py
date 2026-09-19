from __future__ import annotations

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict, Field


class ConversationState(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    messages: list[BaseMessage] = Field(
        default_factory=list,
        description="Conversation message history.",
    )

    summary: str | None = Field(
        default=None,
        description="Condensed summary of the conversation.",
    )

    pending_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Questions that still require user input."
        ),
    )