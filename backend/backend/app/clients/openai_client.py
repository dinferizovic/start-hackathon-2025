from __future__ import annotations

import json
from typing import Any, Dict, List

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings


class OpenAIClient:
    """Thin wrapper around the AsyncOpenAI client with JSON helpers."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
        self._model = settings.openai_model
        self._json_retry = AsyncRetrying(
            wait=wait_exponential(multiplier=0.5, min=1, max=8),
            stop=stop_after_attempt(3),
            retry=retry_if_exception_type((ValueError, RuntimeError)),
            reraise=True,
        )

    async def json_completion(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
        async for attempt in self._json_retry:
            with attempt:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = completion.choices[0].message.content
                if not content:
                    raise RuntimeError("OpenAI response missing content")
                return json.loads(content)
        raise RuntimeError("OpenAI JSON completion failed after retries")

    async def text_completion(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int | None = None,
    ) -> ChatCompletion:
        return await self._client.chat.completions.create(
            model=self._model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system_prompt}, *messages],
        )
