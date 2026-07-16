"""LLM backends.

`LLMBackend` is the seam between the neural and symbolic halves: it takes
a prompt plus a Pydantic model class and must return a validated instance.
`OllamaBackend` enforces the schema at decode time via Ollama structured
outputs (the JSON schema is passed as the `format` parameter), with one
retry that feeds the validation error back to the model.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

import ollama
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "gemma3:4b"


class LLMBackend(Protocol):
    def generate(self, system: str, prompt: str, schema: type[T]) -> T: ...


class OllamaBackend:
    def __init__(self, model: str = DEFAULT_MODEL, retries: int = 1):
        self.model = model
        self.retries = retries

    def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        last_error: Exception | None = None
        for _ in range(self.retries + 1):
            response = ollama.chat(
                model=self.model,
                messages=messages,
                format=schema.model_json_schema(),
                options={"temperature": 0.2},
            )
            content = response["message"]["content"]
            try:
                return schema.model_validate_json(content)
            except ValidationError as e:
                last_error = e
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous JSON failed validation:\n"
                            f"{e}\n\nReturn corrected JSON matching the schema exactly."
                        ),
                    }
                )
        raise RuntimeError(
            f"Model '{self.model}' produced schema-invalid output after "
            f"{self.retries + 1} attempts: {last_error}"
        )
