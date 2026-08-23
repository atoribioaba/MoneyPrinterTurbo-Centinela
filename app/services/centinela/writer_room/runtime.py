from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.services.astronomy_director import (
    AstronomyDirectorError,
    OllamaLocalAdapter,
)

T = TypeVar("T", bound=BaseModel)


class WriterRoomRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedModel:
    value: BaseModel
    request_count: int
    repaired: bool


class WriterRoomOllamaRuntime:
    """Structured, loopback-only runtime. It never downloads models."""

    def __init__(
        self,
        adapter: OllamaLocalAdapter | None = None,
    ) -> None:
        self.adapter = adapter or OllamaLocalAdapter(
            base_url="http://127.0.0.1:11434",
            timeout_seconds=180.0,
        )

    def resolve_model(self, requested: str | None) -> str:
        try:
            return self.adapter.resolve_model(requested)
        except AstronomyDirectorError as exc:
            raise WriterRoomRuntimeError(str(exc)) from exc

    @staticmethod
    def _parse(model_type: type[T], raw: str) -> T:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WriterRoomRuntimeError(
                "Ollama returned malformed structured JSON"
            ) from exc
        try:
            return model_type.model_validate(payload)
        except ValidationError as exc:
            raise WriterRoomRuntimeError(
                f"structured output failed {model_type.__name__} validation: {exc}"
            ) from exc

    def generate(
        self,
        model_type: type[T],
        *,
        model: str,
        prompt: str,
        temperature: float,
    ) -> GeneratedModel:
        schema = model_type.model_json_schema()
        try:
            raw = self.adapter.generate_json(
                model=model,
                prompt=prompt,
                temperature=temperature,
                schema=schema,
            )
            value = self._parse(model_type, raw)
            return GeneratedModel(
                value=value,
                request_count=1,
                repaired=False,
            )
        except (AstronomyDirectorError, WriterRoomRuntimeError) as first:
            repair_prompt = (
                prompt
                + "\n\nLa salida anterior no superó la validación. "
                "Corrige únicamente estructura y contenido para cumplir "
                "exactamente el schema JSON. No añadas markdown. "
                f"ERROR_VALIDACION: {str(first)[:1200]}"
            )
            try:
                raw = self.adapter.generate_json(
                    model=model,
                    prompt=repair_prompt,
                    temperature=0.0,
                    schema=schema,
                )
                value = self._parse(model_type, raw)
            except (AstronomyDirectorError, WriterRoomRuntimeError) as second:
                raise WriterRoomRuntimeError(
                    "Ollama failed structured validation twice: "
                    f"first={str(first)[:700]}; second={str(second)[:700]}"
                ) from second
            return GeneratedModel(
                value=value,
                request_count=2,
                repaired=True,
            )
