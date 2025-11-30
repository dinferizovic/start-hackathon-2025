from __future__ import annotations

from datetime import date
from typing import Dict

from app.schemas.workflow import IntakeSummary, PreferenceWeights, VendorOffer, VendorRoundScore


def _clamp(value: float, *, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class ScoringService:
    def __init__(self, intake: IntakeSummary) -> None:
        self._intake = intake
        self._weights = intake.weights.normalized()

    def score_offer(self, offer: VendorOffer) -> VendorRoundScore:
        breakdown = {
            "price": self._price_score(offer),
            "quality": self._scale_0_to_10(offer.quality_score),
            "delivery": self._delivery_score(offer),
            "prestige": self._scale_0_to_10(offer.brand_reputation_score),
            "sustainability": self._scale_0_to_10(offer.sustainability_score),
        }
        weighted = (
            breakdown["price"] * self._weights.price
            + breakdown["quality"] * self._weights.quality
            + breakdown["delivery"] * self._weights.delivery
            + breakdown["prestige"] * self._weights.prestige
            + breakdown["sustainability"] * self._weights.sustainability
        )
        return VendorRoundScore(round=offer.round, weighted_score=round(weighted, 4), breakdown=breakdown)

    def _price_score(self, offer: VendorOffer) -> float:
        if offer.total_price is None:
            return 0.5
        budget = self._intake.budget
        if budget:
            ratio = budget / max(offer.total_price, 1)
            return _clamp(ratio)
        # fall back to heuristic: assume lower price (< 100k) better
        heuristic = 1 - (offer.total_price / 100000)
        return _clamp(heuristic)

    def _delivery_score(self, offer: VendorOffer) -> float:
        if offer.delivery_days is None:
            return 0.5
        if self._intake.delivery_deadline:
            target_days = max((self._intake.delivery_deadline - date.today()).days, 1)
            slack = target_days - offer.delivery_days
            return _clamp(0.5 + (slack / max(target_days, 1)))
        return _clamp(1 - (offer.delivery_days / 120))

    @staticmethod
    def _scale_0_to_10(value: float | None) -> float:
        if value is None:
            return 0.5
        return _clamp(value / 10)
