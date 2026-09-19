from __future__ import annotations

from pathlib import Path


class PromptService:

    def __init__(self, prompt_directory: Path) -> None:
        self.prompt_directory = prompt_directory
        self._cache: dict[str, str] = {}

    def load(self, prompt_file: str) -> str:
        if prompt_file in self._cache:
            return self._cache[prompt_file]

        path = self._get_prompt_path(prompt_file)

        prompt = self._read_prompt(path)

        self._cache[prompt_file] = prompt

        return prompt

    def clear_cache(self) -> None:
        self._cache.clear()

    def _get_prompt_path(self, prompt_file: str) -> Path:
        path = self.prompt_directory / prompt_file

        if not path.exists():
            raise FileNotFoundError(
                f"Prompt file '{prompt_file}' not found at '{path}'."
            )

        return path

    @staticmethod
    def _read_prompt(path: Path) -> str:
        return path.read_text(encoding="utf-8")
