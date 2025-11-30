from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas.asklio import Conversation, Message, Vendor


class AskLioClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = str(settings.asklio_base_url).rstrip("/")
        self._team_id = settings.asklio_team_id
        self._timeout = settings.asklio_timeout_seconds

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Any:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.request(method, path, params=params, json=json, data=data, files=files)
            response.raise_for_status()
            return response.json()

    async def list_vendors(self) -> List[Vendor]:
        payload = await self._request("GET", "/vendors/", params={"team_id": self._team_id})
        return [Vendor.model_validate(item) for item in payload]

    async def create_conversation(self, vendor_id: int, title: Optional[str] = None) -> Conversation:
        payload = await self._request(
            "POST",
            "/conversations/",
            params={"team_id": self._team_id},
            json={"vendor_id": vendor_id, "title": title},
        )
        return Conversation.model_validate(payload)

    async def send_message(self, conversation_id: int, content: str) -> Message:
        # The AskLio API expects multipart/form-data; send `content` as a pseudo-file part.
        payload = await self._request(
            "POST",
            f"/messages/{conversation_id}",
            files={"content": (None, content)},
        )
        return Message.model_validate(payload)

    async def get_messages(self, conversation_id: int) -> List[Message]:
        payload = await self._request("GET", f"/messages/{conversation_id}")
        return [Message.model_validate(item) for item in payload]

    async def fetch_vendor_subset(self, vendor_ids: Iterable[int]) -> List[Vendor]:
        vendors = await self.list_vendors()
        wanted = set(vendor_ids)
        return [vendor for vendor in vendors if vendor.id in wanted]


def validate_vendor_payload(raw_vendor: Dict[str, Any]) -> Vendor:
    try:
        return Vendor.model_validate(raw_vendor)
    except ValidationError as exc:
        raise RuntimeError("Invalid vendor payload from AskLio") from exc
