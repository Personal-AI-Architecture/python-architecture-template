"""Canonical PAA gateway routes with the TypeScript template's behavior."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypedDict
from urllib.parse import urlsplit

from paa_template.engine import AgentLoop
from paa_template.memory.store import MemoryStore
from paa_template.types import EngineRequest, EngineRequestMetadata, Message


@dataclass
class Conversation:
    id: str
    created_at: str
    updated_at: str
    messages: list[Message]
    title: str | None = None


@dataclass(frozen=True)
class GatewayResponse:
    status: int
    headers: dict[str, str]
    body: dict[str, object] | None = None
    stream: Iterator[dict[str, object]] | None = None


class PublicMessageRequest(TypedDict):
    content: str
    metadata: dict[str, object]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def _header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target and isinstance(value, str) and value.strip():
            return value.strip()
    return None


class ConversationStore:
    def __init__(self, memory: MemoryStore | None = None) -> None:
        self.memory = memory or MemoryStore()
        self.conversations: dict[str, Conversation] = {}

    def create(self, metadata: Mapping[str, object] | None = None) -> Conversation:
        timestamp = _now()
        conversation = Conversation(_new_id("conv"), timestamp, timestamp, [])
        self.conversations[conversation.id] = conversation
        self.memory.record("conversation", {"id": conversation.id, "metadata": dict(metadata or {})})
        return conversation

    def exists(self, conversation_id: str) -> bool:
        return conversation_id in self.conversations

    def append(self, conversation_id: str, message: Message) -> str:
        conversation = self.conversations[conversation_id]
        conversation.messages.append(message)
        conversation.updated_at = _now()
        message_id = _new_id("msg")
        self.memory.record("message", {"id": message_id, "conversation_id": conversation_id, "role": message.role, "content": message.content})
        return message_id

    def list(self) -> list[Conversation]:
        return sorted(self.conversations.values(), key=lambda item: item.updated_at, reverse=True)


class Gateway:
    def __init__(self, engine: AgentLoop, store: ConversationStore | None = None) -> None:
        self.engine = engine
        self.store = store or ConversationStore()

    def handle(
        self,
        method: str,
        path: str,
        *,
        body: object | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> GatewayResponse:
        method = method.upper()
        route = urlsplit(path).path
        if method == "GET" and route == "/conversations":
            conversations = self.store.list()
            return GatewayResponse(200, {"Content-Type": "application/json"}, {
                "conversations": [self._summary(item) for item in conversations],
                "total": len(conversations),
            })
        if method == "GET" and route.startswith("/conversations/"):
            conversation_id = route.split("/")[2]
            conversation = self.store.conversations.get(conversation_id)
            if conversation is None:
                return self._error(404, "conversation_not_found", f"Conversation {conversation_id} was not found.")
            return GatewayResponse(200, {"Content-Type": "application/json"}, self._detail(conversation))
        if method == "POST" and (route == "/conversations/messages" or route == "/chat"):
            return self._message(body, headers or {}, None)
        if method == "POST" and route.startswith("/conversations/") and route.endswith("/messages"):
            conversation_id = route[len("/conversations/") : -len("/messages")].strip("/")
            return self._message(body, headers or {}, conversation_id)
        return self._error(404, "not_found", "Route not found.")

    def _message(self, body: object, headers: Mapping[str, str], requested_id: str | None) -> GatewayResponse:
        parsed = self._parse_public_request(body)
        if parsed is None:
            return self._error(400, "invalid_request", "Request must contain non-empty content and optional metadata.")
        actor_id = _header(headers, "X-Actor-ID")
        actor_permissions = _header(headers, "X-Actor-Permissions")
        if not actor_id or not actor_permissions:
            return self._error(401, "missing_actor_headers", "Missing required actor headers.")
        if requested_id is not None and not self.store.exists(requested_id):
            return self._error(404, "conversation_not_found", f"Conversation {requested_id} was not found.")

        conversation = self.store.conversations[requested_id] if requested_id else self.store.create(parsed.get("metadata"))
        user_message = Message("user", parsed["content"])
        self.store.append(conversation.id, user_message)
        metadata = parsed.get("metadata") or {}
        engine_request = EngineRequest(
            messages=tuple(conversation.messages),
            metadata=EngineRequestMetadata(
                correlation_id=str(metadata.get("correlation_id") or _new_id("corr")),
                conversation_id=conversation.id,
                actor_id=actor_id,
                actor_permissions=tuple(item.strip() for item in actor_permissions.split(",") if item.strip()),
            ),
        )
        return GatewayResponse(
            200,
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Conversation-ID": conversation.id,
            },
            stream=self._stream_and_persist(conversation.id, engine_request, {"X-Actor-ID": actor_id, "X-Actor-Permissions": actor_permissions}),
        )

    def _stream_and_persist(self, conversation_id: str, request: EngineRequest, actor_headers: Mapping[str, str]) -> Iterator[dict[str, object]]:
        text_parts: list[str] = []
        for event in self.engine.run(request, actor_headers):
            data = dict(event.data)
            if event.event == "text-delta":
                text_parts.append(str(data.get("text", "")))
            if event.event == "done":
                data.setdefault("finish_reason", "stop")
                data.setdefault("message_id", _new_id("msg"))
                if text_parts:
                    self.store.append(conversation_id, Message("assistant", "".join(text_parts)))
            yield {"event": event.event, "data": data}

    @staticmethod
    def _parse_public_request(body: object) -> PublicMessageRequest | None:
        if not isinstance(body, Mapping) or "messages" in body:
            return None
        if set(body) - {"content", "metadata"}:
            return None
        content = body.get("content")
        metadata = body.get("metadata", {})
        if not isinstance(content, str) or not content.strip() or not isinstance(metadata, Mapping):
            return None
        return {"content": content, "metadata": dict(metadata)}

    @staticmethod
    def _summary(conversation: Conversation) -> dict[str, object]:
        return {"id": conversation.id, "created_at": conversation.created_at, "updated_at": conversation.updated_at, "message_count": len(conversation.messages)}

    @staticmethod
    def _detail(conversation: Conversation) -> dict[str, object]:
        return {
            "id": conversation.id,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": [{"id": _new_id("msg"), "role": message.role, "content": message.content, "created_at": conversation.updated_at} for message in conversation.messages],
        }

    @staticmethod
    def _error(status: int, code: str, message: str) -> GatewayResponse:
        return GatewayResponse(status, {"Content-Type": "application/json"}, {"error": {"code": code, "message": message}})
