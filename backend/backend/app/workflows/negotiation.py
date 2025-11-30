from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, is_dataclass
import re
from textwrap import dedent
from typing import Any, List, Literal, Optional, Sequence

from pydantic import BaseModel

from app.clients.asklio import AskLioClient
from app.clients.openai_client import OpenAIClient
from app.config import Settings, get_settings
from app.schemas.asklio import Message, Vendor
from app.schemas.workflow import (
    IntakeSummary,
    NegotiationRequest,
    NegotiationResponse,
    TradeoffOption,
    VendorOffer,
    VendorOutcome,
    VendorRoundScore,
)
from app.services.intake import IntakeService
from app.services.scoring import ScoringService

logger = logging.getLogger("negotiation.workflow")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


@dataclass
class _VendorRound:
    vendor: Vendor
    conversation_id: int
    first_message: Message
    first_offer: VendorOffer
    first_score: VendorRoundScore


class NegotiationWorkflow:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._asklio = AskLioClient(self._settings)
        self._openai = OpenAIClient(self._settings)
        self._intake_service = IntakeService(self._openai)
        self._logger = logger

    async def run(self, request: NegotiationRequest) -> NegotiationResponse:
        self._log("request_received", request=request)
        intake_summary = await self._intake_service.build_summary(request.intake)
        self._log("intake_summary", summary=intake_summary)
        scoring = ScoringService(intake_summary)
        vendors = await self._pick_vendors(request, limit=request.vendor_limit)
        self._log(
            "selected_vendors",
            vendor_ids=[vendor.id for vendor in vendors],
            vendor_names=[vendor.name for vendor in vendors],
        )
        if not vendors:
            raise RuntimeError("No vendors available from AskLio")

        first_round = []
        for vendor in vendors:
            self._log("initial_round_start", vendor_id=vendor.id, vendor_name=vendor.name)
            conversation = await self._asklio.create_conversation(
                vendor_id=vendor.id,
                title=f"{intake_summary.items[0].name} negotiation",
            )
            self._log(
                "conversation_created",
                vendor_id=vendor.id,
                vendor_name=vendor.name,
                conversation_id=conversation.id,
            )
            initial_prompt = self._build_initial_prompt(vendor, intake_summary)
            self._log(
                "initial_prompt",
                vendor_id=vendor.id,
                conversation_id=conversation.id,
                prompt=initial_prompt,
            )
            vendor_response = await self._asklio.send_message(conversation.id, initial_prompt)
            self._log(
                "vendor_response_initial",
                vendor_id=vendor.id,
                conversation_id=conversation.id,
                response=vendor_response,
            )
            offer = await self._extract_offer_with_fallback(
                vendor, vendor_response, conversation.id, round_name="initial"
            )
            self._log(
                "initial_offer_extracted",
                vendor_id=vendor.id,
                conversation_id=conversation.id,
                offer=offer,
            )
            score = scoring.score_offer(offer)
            self._log(
                "initial_score",
                vendor_id=vendor.id,
                conversation_id=conversation.id,
                score=score,
            )
            first_round.append(
                _VendorRound(
                    vendor=vendor,
                    conversation_id=conversation.id,
                    first_message=vendor_response,
                    first_offer=offer,
                    first_score=score,
                )
            )

        shortlisted = sorted(first_round, key=lambda item: item.first_score.weighted_score, reverse=True)[
            : self._settings.second_round_limit
        ]
        self._log(
            "shortlist_ready",
            shortlisted_vendor_ids=[entry.vendor.id for entry in shortlisted],
            shortlisted_vendor_names=[entry.vendor.name for entry in shortlisted],
        )

        shortlisted_outcomes: List[VendorOutcome] = []
        for round_entry in shortlisted:
            strategy, second_prompt = await self._build_second_round_prompt(round_entry, intake_summary)
            self._log(
                "second_round_strategy",
                vendor_id=round_entry.vendor.id,
                conversation_id=round_entry.conversation_id,
                strategy=strategy,
            )
            self._log(
                "second_round_prompt",
                vendor_id=round_entry.vendor.id,
                conversation_id=round_entry.conversation_id,
                prompt=second_prompt,
            )
            second_message = await self._asklio.send_message(round_entry.conversation_id, second_prompt)
            self._log(
                "vendor_response_second",
                vendor_id=round_entry.vendor.id,
                conversation_id=round_entry.conversation_id,
                response=second_message,
            )
            second_offer = await self._extract_offer_with_fallback(
                round_entry.vendor,
                second_message,
                round_entry.conversation_id,
                round_name="second",
            )
            second_score = scoring.score_offer(second_offer)
            self._log(
                "second_offer_extracted",
                vendor_id=round_entry.vendor.id,
                conversation_id=round_entry.conversation_id,
                offer=second_offer,
            )
            self._log(
                "second_score",
                vendor_id=round_entry.vendor.id,
                conversation_id=round_entry.conversation_id,
                score=second_score,
            )
            shortlisted_outcomes.append(
                VendorOutcome(
                    vendor_id=round_entry.vendor.id,
                    vendor_name=round_entry.vendor.name,
                    conversation_id=round_entry.conversation_id,
                    strategy=strategy,
                    initial_offer=round_entry.first_offer,
                    second_offer=second_offer,
                    scores=[round_entry.first_score, second_score],
                )
            )

        tradeoffs = self._build_tradeoff_options(shortlisted_outcomes)
        self._log("tradeoff_options_ready", options=tradeoffs)
        response = NegotiationResponse(
            intake_summary=intake_summary,
            shortlisted_vendors=shortlisted_outcomes,
            tradeoff_options=tradeoffs,
        )
        self._log("workflow_complete", response=response)
        return response

    async def _pick_vendors(self, request: NegotiationRequest, limit: Optional[int]) -> List[Vendor]:
        limit = limit or self._settings.max_parallel_vendors
        if request.vendor_ids:
            vendors = await self._asklio.fetch_vendor_subset(request.vendor_ids)
        else:
            vendors = await self._asklio.list_vendors()
        return vendors[:limit]

    def _build_initial_prompt(self, vendor: Vendor, intake: IntakeSummary) -> str:
        items_section = "\n".join(
            f"- {item.quantity} x {item.name}" + (f" ({item.notes})" if item.notes else "")
            for item in intake.items
        )
        constraint_section = "None" if not intake.constraints else "; ".join(intake.constraints)
        location = intake.location or "TBD"
        budget = f"${intake.budget:,.0f}" if intake.budget else "flexible"
        delivery = intake.delivery_deadline.isoformat() if intake.delivery_deadline else "need your soonest"

        return dedent(
            f"""
            Hello {vendor.name} team,

            We are sourcing the following items:
            {items_section}

            Budget: {budget}
            Delivery target: {delivery}
            Ship to: {location}
            Additional constraints: {constraint_section}

            Please share your best all-in offer including:
            - Total price (with currency)
            - Delivery timeline in days
            - Warranty coverage
            - Quality or sustainability highlights
            - Any extras you can include (installation, training, etc.)
            """
        ).strip()

    async def _extract_offer(
        self,
        vendor: Vendor,
        vendor_message: Message,
        conversation_id: int,
        *,
        round_name: Literal["initial", "second"],
    ) -> VendorOffer:
        system_prompt = "You read vendor replies and summarize them into a structured offer JSON."
        user_payload = json.dumps(
            {
                "vendor_name": vendor.name,
                "vendor_message": vendor_message.content,
                "expected_fields": [
                    "total_price",
                    "currency",
                    "delivery_days",
                    "warranty_months",
                    "quality_score",
                    "sustainability_score",
                    "brand_reputation_score",
                    "extras",
                ],
            }
        )
        response = await self._openai.json_completion(system_prompt, user_payload)
        return VendorOffer(
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            round=round_name,
            conversation_id=conversation_id,
            message_id=vendor_message.id,
            raw_message=vendor_message.content,
            total_price=self._coerce_float(response.get("total_price")),
            currency=response.get("currency"),
            delivery_days=self._coerce_int(response.get("delivery_days")),
            warranty_months=self._coerce_int(response.get("warranty_months")),
            quality_score=self._coerce_float(response.get("quality_score")),
            sustainability_score=self._coerce_float(response.get("sustainability_score")),
            brand_reputation_score=self._coerce_float(response.get("brand_reputation_score")),
            extras=self._normalize_extras(response.get("extras")),
        )

    async def _build_second_round_prompt(
        self,
        round_entry: _VendorRound,
        intake: IntakeSummary,
    ) -> tuple[str, str]:
        system_prompt = dedent(
            """
            You are a negotiation strategist. Given the intake summary and vendor offer, craft:
            - `strategy`: short guidance on tone + levers
            - `message`: final negotiation message to send to the vendor. Mention price, delivery, and extras.
            Respond as JSON.
            """
        ).strip()

        payload = {
            "customer_intake": intake.model_dump(mode="json"),
            "vendor_name": round_entry.vendor.name,
            "vendor_response": round_entry.first_message.content,
            "parsed_offer": round_entry.first_offer.model_dump(mode="json"),
        }
        try:
            result = await self._openai.json_completion(system_prompt, json.dumps(payload))
        except Exception:
            self._logger.exception(
                "second_round_prompt_failed | vendor_id=%s conversation_id=%s",
                round_entry.vendor.id,
                round_entry.conversation_id,
            )
            return (
                "Fallback: collaborative but firm",
                self._fallback_second_round_message(round_entry, intake),
            )

        strategy = self._stringify_field(result.get("strategy")) or "Collaborative but firm"
        message = self._stringify_field(result.get("message"))
        if not message:
            message = self._fallback_second_round_message(round_entry, intake)
        return strategy, message

    def _fallback_second_round_message(self, round_entry: _VendorRound, intake: IntakeSummary) -> str:
        target_price = "our budget" if not intake.budget else f"staying close to ${intake.budget:,.0f}"
        delivery = intake.delivery_deadline.isoformat() if intake.delivery_deadline else "your fastest lead time"
        return dedent(
            f"""
            Thanks for the detailed proposal. To move forward we need:
            - A sharper price closer to {target_price}
            - Delivery before {delivery}
            - Extras such as training or extended warranty if possible
            Please review and share your best revision.
            """
        ).strip()

    async def _extract_offer_with_fallback(
        self,
        vendor: Vendor,
        vendor_message: Message,
        conversation_id: int,
        *,
        round_name: Literal["initial", "second"],
    ) -> VendorOffer:
        try:
            return await self._extract_offer(
                vendor,
                vendor_message,
                conversation_id,
                round_name=round_name,
            )
        except Exception as exc:
            self._logger.exception(
                "offer_extraction_failed | vendor_id=%s conversation_id=%s round=%s",
                vendor.id,
                conversation_id,
                round_name,
            )
            return VendorOffer(
                vendor_id=vendor.id,
                vendor_name=vendor.name,
                round=round_name,
                conversation_id=conversation_id,
                message_id=vendor_message.id,
                raw_message=vendor_message.content,
                extras=[],
            )

    def _log(self, step: str, **data: Any) -> None:
        if not self._logger.isEnabledFor(logging.INFO):
            return
        try:
            serialized = {key: self._serialize(value) for key, value in data.items()}
            self._logger.info("%s | %s", step, json.dumps(serialized, ensure_ascii=False, default=str))
        except Exception:
            self._logger.info("%s | %s", step, data)

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump()
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, dict):
            return {key: self._serialize(val) for key, val in value.items()}
        return value

    def _numeric_from_string(self, value: str) -> float | None:
        sanitized = value.replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", sanitized)
        if not match:
            return None
        try:
            return float(match.group())
        except ValueError:
            return None

    def _coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return self._numeric_from_string(value)
        return None

    def _coerce_int(self, value: Any) -> int | None:
        numeric = self._coerce_float(value)
        if numeric is None:
            return None
        return int(numeric)

    def _normalize_extras(self, extras: Any) -> List[str]:
        if extras is None:
            return []
        if isinstance(extras, str):
            return [extras]
        if isinstance(extras, list):
            normalized: List[str] = []
            for item in extras:
                normalized.extend(self._normalize_extras(item))
            return normalized
        if isinstance(extras, dict):
            normalized_items = []
            for key, value in extras.items():
                if isinstance(value, (dict, list)):
                    normalized_items.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
                else:
                    normalized_items.append(f"{key}: {value}")
            return normalized_items
        return [str(extras)]

    def _stringify_field(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value)

    def _build_tradeoff_options(self, outcomes: Sequence[VendorOutcome]) -> List[TradeoffOption]:
        if not outcomes:
            return []

        def final_score(outcome: VendorOutcome) -> float:
            return outcome.scores[-1].weighted_score if outcome.scores else 0.0

        def second_offer_or_initial(outcome: VendorOutcome) -> VendorOffer:
            return outcome.second_offer or outcome.initial_offer

        best_price = min(
            outcomes,
            key=lambda o: (second_offer_or_initial(o).total_price or float("inf")),
            default=None,
        )
        best_quality = max(
            outcomes,
            key=lambda o: (second_offer_or_initial(o).quality_score or 0.0),
            default=None,
        )
        fastest_delivery = min(
            outcomes,
            key=lambda o: (second_offer_or_initial(o).delivery_days or float("inf")),
            default=None,
        )
        balanced = max(outcomes, key=final_score)

        options: List[TradeoffOption] = []
        if best_price:
            offer = second_offer_or_initial(best_price)
            price_text = "N/A"
            if offer.total_price is not None:
                formatted_price = f"{offer.total_price:,.0f}" if offer.total_price > 100 else f"{offer.total_price}"
                price_text = f"{offer.currency or ''} {formatted_price}".strip()
            options.append(
                TradeoffOption(
                    label="Best Price",
                    vendor_id=best_price.vendor_id,
                    vendor_name=best_price.vendor_name,
                    summary=price_text,
                    rationale="Lowest total investment after two rounds.",
                )
            )
        if best_quality:
            offer = second_offer_or_initial(best_quality)
            options.append(
                TradeoffOption(
                    label="Best Quality",
                    vendor_id=best_quality.vendor_id,
                    vendor_name=best_quality.vendor_name,
                    summary=f"Quality score {offer.quality_score or 'n/a'}",
                    rationale="Highest quality/brand metrics from the final offers.",
                )
            )
        if fastest_delivery:
            offer = second_offer_or_initial(fastest_delivery)
            options.append(
                TradeoffOption(
                    label="Fastest Delivery",
                    vendor_id=fastest_delivery.vendor_id,
                    vendor_name=fastest_delivery.vendor_name,
                    summary=f"{offer.delivery_days or 'n/a'} days",
                    rationale="Quickest confirmed delivery timeline.",
                )
            )
        if balanced:
            offer = second_offer_or_initial(balanced)
            options.append(
                TradeoffOption(
                    label="Balanced",
                    vendor_id=balanced.vendor_id,
                    vendor_name=balanced.vendor_name,
                    summary=f"Weighted score {final_score(balanced):.2f}",
                    rationale="Best composite score across price, quality, delivery, prestige, and sustainability.",
                )
            )
        return options


def get_workflow() -> NegotiationWorkflow:
    return NegotiationWorkflow()
