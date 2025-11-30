from __future__ import annotations

import json
from textwrap import dedent
from typing import Any, Dict, List

from app.clients.openai_client import OpenAIClient
from app.schemas.workflow import IntakePayload, IntakeSummary, ItemRequest, PreferenceWeights


class IntakeService:
    def __init__(self, openai_client: OpenAIClient) -> None:
        self._openai = openai_client

    async def build_summary(self, payload: IntakePayload) -> IntakeSummary:
        system_prompt = dedent(
            """
            You are an intake specialist for a procurement negotiation bot.
            Read the user's request and any known details, then produce a JSON object with:
            - `items`: array of {name, quantity, notes}
            - `budget`: total budget in numeric form when supplied or inferred
            - `delivery_deadline`: ISO date when mentioned
            - `location`: city/country or delivery location
            - `weights`: object with price, quality, delivery, prestige, sustainability (numbers 0-1)
            - `constraints`: array of textual constraints (e.g. warranty >= 2 years)
            - `clarifying_questions`: follow-up questions still needed
            - `missing_information`: short bullet list of what is still unknown
            - `rationale`: short explanation of how you interpreted the request.
            Always respond with valid JSON only.
            """
        ).strip()

        user_prompt = json.dumps(payload.model_dump(), default=str)
        suggestion = await self._openai.json_completion(system_prompt, user_prompt)

        items_data = suggestion.get("items") or payload.items or []
        items = [ItemRequest.model_validate(item) for item in items_data]
        if not items:
            raise ValueError("No items were identified from the intake request")

        weights_data = suggestion.get("weights") or payload.weights or PreferenceWeights()
        weights = PreferenceWeights.model_validate(weights_data).normalized()

        constraints = suggestion.get("constraints") or payload.constraints or []

        return IntakeSummary(
            items=items,
            budget=suggestion.get("budget") or payload.budget,
            delivery_deadline=suggestion.get("delivery_deadline") or payload.delivery_deadline,
            location=suggestion.get("location") or payload.location,
            weights=weights,
            constraints=constraints,
            clarifying_questions=suggestion.get("clarifying_questions", []),
            missing_information=suggestion.get("missing_information", []),
            rationale=suggestion.get("rationale"),
        )
