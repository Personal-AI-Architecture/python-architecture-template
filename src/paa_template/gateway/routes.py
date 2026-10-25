"""Canonical PAA gateway routes with the TypeScript template's behavior."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, TypedDict
from urllib.parse import parse_qs, urlsplit

from paa_template.engine import AgentLoop
from paa_template.memory.store import MemoryStore
from paa_template.types import EngineRequest, EngineRequestMetadata, Message
from paa_template.types.context import model_limit, select_complete_turns


@dataclass
class Conversation:
    id: str
    created_at: str
    updated_at: str
    messages: list[Message]
    message_details: list[dict[str, str]]
    title: str | None = None


@dataclass(frozen=True)
class GatewayResponse:
    status: int
    headers: dict[str, str]
    body: dict[str, object] | None = None
    stream: Iterator[dict[str, object]] | None = None


class PublicMessageRequest(TypedDict):
    content: tuple[dict[str, object], ...]
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
    def __init__(self, memory: MemoryStore | None = None, persistence_path: str | None = None) -> None:
        self.memory = memory or MemoryStore()
        self.conversations: dict[str, Conversation] = {}
        self.persistence_path = Path(persistence_path) if persistence_path else None
        if self.persistence_path and self.persistence_path.exists():
            saved = json.loads(self.persistence_path.read_text(encoding="utf-8"))
            for item in saved.get("conversations", []):
                messages = [Message(entry["role"], tuple(entry["content"])) for entry in item["messages"]]
                conversation = Conversation(item["id"], item["created_at"], item["updated_at"], messages, item["message_details"], item.get("title"))
                self.conversations[conversation.id] = conversation

    def _save(self) -> None:
        if self.persistence_path is None:
            return
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"conversations": [{"id": item.id, "created_at": item.created_at, "updated_at": item.updated_at,
                                      "messages": [{"role": message.role, "content": list(message.parts)} for message in item.messages],
                                      "message_details": item.message_details, "title": item.title}
                                     for item in self.conversations.values()]}
        temporary = self.persistence_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.persistence_path)

    def create(self, metadata: Mapping[str, object] | None = None) -> Conversation:
        timestamp = _now()
        conversation = Conversation(_new_id("conv"), timestamp, timestamp, [], [])
        self.conversations[conversation.id] = conversation
        self.memory.record("conversation", {"id": conversation.id, "metadata": dict(metadata or {})})
        self._save()
        return conversation

    def exists(self, conversation_id: str) -> bool:
        return conversation_id in self.conversations

    def append(self, conversation_id: str, message: Message, *, model: str | None = None, provider: str | None = None) -> str:
        conversation = self.conversations[conversation_id]
        conversation.messages.append(message)
        conversation.updated_at = _now()
        message_id = _new_id("msg")
        detail = {"id": message_id, "created_at": conversation.updated_at}
        if message.role == "assistant":
            if not model or not provider:
                raise ValueError("Assistant replies require model and provider provenance.")
            detail.update({"model": model, "provider": provider})
        conversation.message_details.append(detail)
        self.memory.record("message", {"id": message_id, "conversation_id": conversation_id, "role": message.role, "content": message.content, **detail})
        self._save()
        return message_id

    def list(self) -> list[Conversation]:
        return sorted(self.conversations.values(), key=lambda item: item.updated_at, reverse=True)


class Gateway:
    def __init__(self, engine: AgentLoop, store: ConversationStore | None = None, current_model: Callable[[], str] | None = None, current_provider: Callable[[], str] | None = None) -> None:
        self.engine = engine
        self.store = store or ConversationStore()
        self.current_model = current_model or (lambda: "mock")
        self.current_provider = current_provider or (lambda: "local")

    def handle(
        self,
        method: str,
        path: str,
        *,
        body: object | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> GatewayResponse:
        method = method.upper()
        parsed_url = urlsplit(path)
        route = parsed_url.path
        if method == "GET" and route == "/conversations":
            query = parse_qs(parsed_url.query)
            try:
                limit = int(query.get("limit", ["20"])[0])
                offset = int(query.get("offset", ["0"])[0])
                if not 1 <= limit <= 100 or offset < 0:
                    raise ValueError("Invalid pagination")
                after = datetime.fromisoformat(query["from"][0].replace("Z", "+00:00")) if "from" in query else None
                before = datetime.fromisoformat(query["to"][0].replace("Z", "+00:00")) if "to" in query else None
            except (ValueError, KeyError):
                return self._error(400, "invalid_request", "Invalid conversation filter.")
            search = query.get("search", [""])[0].lower()
            conversations = [item for item in self.store.list()
                             if (not search or search in (json.dumps([message.content for message in item.messages]) + (item.title or "")).lower())
                             and (after is None or datetime.fromisoformat(item.created_at) >= after)
                             and (before is None or datetime.fromisoformat(item.created_at) <= before)]
            return GatewayResponse(200, {"Content-Type": "application/json"}, {
                "conversations": [self._summary(item) for item in conversations[offset:offset + limit]],
                "total": len(conversations),
                "limit": limit,
                "offset": offset,
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
        model, provider = self.current_model(), self.current_provider()
        limit = model_limit(self.engine.context_limits, provider, model)
        if limit is None:
            return self._error(503, "context_limit_unknown", "No safe context limit for selected provider and model.")
        selected, omitted = select_complete_turns(tuple(conversation.messages), limit, self.engine.tools)
        if selected is None:
            return self._error(422, "context_overflow", "Current message exceeds the selected model context window.")
        metadata = parsed.get("metadata") or {}
        correlation_id = str(metadata.get("correlation_id") or _new_id("corr"))
        engine_request = EngineRequest(
            messages=selected,
            metadata=EngineRequestMetadata(
                correlation_id=correlation_id,
                conversation_id=conversation.id,
                client_context=dict(metadata),
            ),
            model=model,
            provider=provider,
            auth_context={
                "actor": {"id": actor_id, "type": "owner", "display_name": actor_id, "status": "active", "created": _now()},
                "authentication_id": _new_id("authn"),
                "authenticated_at": _now(),
                "correlation_id": correlation_id,
            },
        )
        return GatewayResponse(
            200,
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Conversation-ID": conversation.id,
            },
            stream=self._stream_and_persist(conversation.id, engine_request, omitted),
        )

    def _stream_and_persist(self, conversation_id: str, request: EngineRequest, omitted: int = 0) -> Iterator[dict[str, object]]:
        text_parts: list[str] = []
        if omitted:
            yield {"event": "context_notice", "data": {"_event_type": "context_notice", "action": "omitted", "omitted_turn_count": omitted, "message": "Older conversation turns were omitted from this reply's working context."}}
        for event in self.engine.run(request):
            data = dict(event.data)
            if event.event == "text-delta":
                text_parts.append(str(data.get("content", "")))
            if event.event == "done":
                data.setdefault("finish_reason", "stop")
                data["message_id"] = self.store.append(conversation_id, Message("assistant", "".join(text_parts)), model=request.model, provider=request.provider)
            data["_event_type"] = event.event
            yield {"event": event.event, "data": data}

    @staticmethod
    def _parse_public_request(body: object) -> PublicMessageRequest | None:
        if not isinstance(body, Mapping) or "messages" in body:
            return None
        if set(body) - {"content", "metadata"}:
            return None
        content = body.get("content")
        metadata = body.get("metadata", {})
        if not isinstance(content, list) or not content or not isinstance(metadata, Mapping):
            return None
        parts: list[dict[str, object]] = []
        for part in content:
            if not isinstance(part, Mapping) or part.get("type") not in {"text", "image", "file"}:
                return None
            if "extensions" in part and not isinstance(part["extensions"], Mapping):
                return None
            allowed = {"type", "text", "extensions"} if part["type"] == "text" else {"type", "url", "name", "mime_type", "extensions"}
            if set(part) - allowed:
                return None
            if part["type"] == "text" and not isinstance(part.get("text"), str):
                return None
            if part["type"] in {"image", "file"} and not isinstance(part.get("url"), str):
                return None
            parts.append(dict(part))
        return {"content": tuple(parts), "metadata": dict(metadata)}

    @staticmethod
    def _summary(conversation: Conversation) -> dict[str, object]:
        return {"id": conversation.id, "created_at": conversation.created_at, "updated_at": conversation.updated_at, "message_count": len(conversation.messages)}

    @staticmethod
    def _detail(conversation: Conversation) -> dict[str, object]:
        return {
            "id": conversation.id,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": [{"role": message.role, "content": list(message.parts), **detail} for message, detail in zip(conversation.messages, conversation.message_details)],
        }

    @staticmethod
    def _error(status: int, code: str, message: str) -> GatewayResponse:
        return GatewayResponse(status, {"Content-Type": "application/json"}, {"code": code, "message": message})
