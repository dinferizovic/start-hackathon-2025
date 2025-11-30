from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ItemRequest(BaseModel):
    name: str
    quantity: int = Field(ge=1)
    notes: Optional[str] = None


class PreferenceWeights(BaseModel):
    price: float = Field(default=0.35, ge=0, le=1)
    quality: float = Field(default=0.2, ge=0, le=1)
    delivery: float = Field(default=0.2, ge=0, le=1)
    prestige: float = Field(default=0.15, ge=0, le=1)
    sustainability: float = Field(default=0.1, ge=0, le=1)

    def normalized(self) -> "PreferenceWeights":
        total = self.price + self.quality + self.delivery + self.prestige + self.sustainability
        if total == 0:
            return self
        return PreferenceWeights(
            price=self.price / total,
            quality=self.quality / total,
            delivery=self.delivery / total,
            prestige=self.prestige / total,
            sustainability=self.sustainability / total,
        )


class IntakePayload(BaseModel):
    initial_request: str = Field(description="Raw text provided by the user")
    items: Optional[List[ItemRequest]] = None
    budget: Optional[float] = None
    delivery_deadline: Optional[date] = None
    location: Optional[str] = None
    weights: Optional[PreferenceWeights] = None
    constraints: Optional[List[str]] = None


class IntakeSummary(BaseModel):
    items: List[ItemRequest]
    budget: Optional[float] = None
    delivery_deadline: Optional[date] = None
    location: Optional[str] = None
    weights: PreferenceWeights
    constraints: List[str] = Field(default_factory=list)
    clarifying_questions: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    rationale: Optional[str] = None


class VendorOffer(BaseModel):
    vendor_id: int
    vendor_name: str
    round: Literal["initial", "second"]
    conversation_id: int
    message_id: int
    raw_message: str
    total_price: Optional[float] = None
    currency: Optional[str] = None
    delivery_days: Optional[int] = None
    warranty_months: Optional[int] = None
    quality_score: Optional[float] = None
    sustainability_score: Optional[float] = None
    brand_reputation_score: Optional[float] = None
    extras: List[str] = Field(default_factory=list)


class VendorRoundScore(BaseModel):
    round: Literal["initial", "second"]
    weighted_score: float
    breakdown: Dict[str, float]
    notes: Optional[str] = None


class VendorOutcome(BaseModel):
    vendor_id: int
    vendor_name: str
    conversation_id: int
    strategy: str
    initial_offer: VendorOffer
    second_offer: Optional[VendorOffer] = None
    scores: List[VendorRoundScore]


class TradeoffOption(BaseModel):
    label: Literal["Best Price", "Best Quality", "Fastest Delivery", "Balanced"]
    vendor_id: int
    vendor_name: str
    summary: str
    rationale: str


class NegotiationRequest(BaseModel):
    intake: IntakePayload
    vendor_ids: Optional[List[int]] = Field(
        default=None, description="Subset of vendor IDs to use; defaults to the AskLio catalog"
    )
    vendor_limit: Optional[int] = Field(default=None, description="Hard limit on vendors to contact")


class NegotiationResponse(BaseModel):
    intake_summary: IntakeSummary
    shortlisted_vendors: List[VendorOutcome]
    tradeoff_options: List[TradeoffOption]
