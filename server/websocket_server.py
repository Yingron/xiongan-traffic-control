"""30-intersection WebSocket transport for the REST/TraCI session manager.

The WebSocket endpoint deliberately shares the same session manager as the
REST API.  It does not load a policy or generate actions: callers must submit
all thirty actions explicitly until A delivers a versioned DQN artifact.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError


ALLOWED_CHANNELS = frozenset({"state", "reward"})


@dataclass(frozen=True)
class Subscription:
    session_id: str
    channels: frozenset[str]


class WebSocketHub:
    """Manage subscribers and translate WebSocket messages to manager calls."""

    def __init__(
        self,
        manager: Any,
        actions_request_type: type,
        api_error_type: type[Exception],
        *,
        heartbeat_seconds: float = 10.0,
    ) -> None:
        self.manager = manager
        self.actions_request_type = actions_request_type
        self.api_error_type = api_error_type
        self.heartbeat_seconds = heartbeat_seconds
        self._subscriptions: dict[WebSocket, Subscription] = {}
        self._send_locks: dict[WebSocket, asyncio.Lock] = {}

    @property
    def connection_count(self) -> int:
        return len(self._subscriptions)

    def register(self, app: FastAPI, path: str) -> None:
        @app.websocket(path)
        async def websocket_endpoint(websocket: WebSocket) -> None:
            await self.handle(websocket)

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._send_locks[websocket] = asyncio.Lock()
        heartbeat = asyncio.create_task(self._heartbeat_loop(websocket))
        try:
            while True:
                raw_message = await websocket.receive_text()
                await self._handle_message(websocket, raw_message)
        except WebSocketDisconnect:
            pass
        finally:
            heartbeat.cancel()
            self._remove(websocket)
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _handle_message(self, websocket: WebSocket, raw_message: str) -> None:
        request_id: Any = None
        try:
            message = json.loads(raw_message)
            if not isinstance(message, dict):
                raise ValueError("message must be a JSON object")
            request_id = message.get("request_id")
        except (json.JSONDecodeError, ValueError) as error:
            await self._send_error(
                websocket,
                "INVALID_MESSAGE",
                "WebSocket messages must be JSON objects.",
                details={"reason": str(error)},
            )
            return

        message_type = message.get("type")
        if message_type == "subscribe":
            await self._subscribe(websocket, message)
        elif message_type == "simulation.actions":
            await self._execute_actions(websocket, message)
        elif message_type == "ping":
            await self._send(
                websocket,
                {"type": "pong", "request_id": request_id, "timestamp": int(time.time() * 1000)},
            )
        else:
            await self._send_error(
                websocket,
                "UNSUPPORTED_MESSAGE",
                "Supported message types are subscribe, simulation.actions, and ping.",
                request_id=request_id,
                details={"received_type": message_type},
            )

    async def _subscribe(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        request_id = message.get("request_id")
        session_id = message.get("session_id")
        channels = message.get("channels", ["state", "reward"])
        if not isinstance(session_id, str) or not session_id:
            await self._send_error(
                websocket,
                "INVALID_SUBSCRIPTION",
                "session_id must be a non-empty string.",
                request_id=request_id,
            )
            return
        if (
            not isinstance(channels, list)
            or not channels
            or any(not isinstance(channel, str) for channel in channels)
        ):
            await self._send_error(
                websocket,
                "INVALID_SUBSCRIPTION",
                "channels must be a non-empty array containing state and/or reward.",
                request_id=request_id,
            )
            return
        normalized_channels = frozenset(channels)
        unknown_channels = normalized_channels - ALLOWED_CHANNELS
        if unknown_channels:
            await self._send_error(
                websocket,
                "INVALID_SUBSCRIPTION",
                "Only state and reward channels are supported.",
                request_id=request_id,
                details={"unsupported_channels": sorted(unknown_channels)},
            )
            return

        try:
            snapshot = await self.manager.stream_snapshot(session_id, normalized_channels)
        except self.api_error_type as error:
            await self._send_api_error(websocket, error, request_id)
            return

        self._subscriptions[websocket] = Subscription(session_id, normalized_channels)
        await self._send(
            websocket,
            {
                "type": "subscription.confirmed",
                "request_id": request_id,
                "session_id": session_id,
                "channels": sorted(normalized_channels),
            },
        )
        await self._send(websocket, snapshot)

    async def _execute_actions(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        request_id = message.get("request_id")
        try:
            request = self.actions_request_type(
                session_id=message.get("session_id"),
                expected_transition_id=message.get("expected_transition_id"),
                actions=message.get("actions"),
                step_seconds=message.get("step_seconds", 5),
            )
            result = await self.manager.actions(request)
        except ValidationError as error:
            validation_errors = [
                {
                    "loc": list(item.get("loc", ())),
                    "msg": item.get("msg"),
                    "type": item.get("type"),
                }
                for item in error.errors()
            ]
            await self._send_error(
                websocket,
                "INVALID_ACTION_SET",
                "Actions must contain exactly J01 through J30 with integer values from 0 to 3.",
                request_id=request_id,
                details={"validation_errors": validation_errors},
            )
            return
        except self.api_error_type as error:
            await self._send_api_error(websocket, error, request_id)
            return

        await self._send(
            websocket,
            {"type": "simulation.action_result", "request_id": request_id, **result},
        )
        await self.broadcast_snapshot(request.session_id)

    async def broadcast_snapshot(self, session_id: str) -> None:
        recipients = [
            (websocket, subscription)
            for websocket, subscription in list(self._subscriptions.items())
            if subscription.session_id == session_id
        ]
        for websocket, subscription in recipients:
            try:
                snapshot = await self.manager.stream_snapshot(session_id, subscription.channels)
                await self._send(websocket, snapshot)
            except self.api_error_type as error:
                try:
                    await self._send_api_error(websocket, error)
                except (WebSocketDisconnect, RuntimeError):
                    self._remove(websocket)
            except (WebSocketDisconnect, RuntimeError):
                self._remove(websocket)

    async def broadcast_event(self, session_id: str, payload: dict[str, Any], *, unsubscribe: bool = False) -> None:
        recipients = [
            websocket
            for websocket, subscription in list(self._subscriptions.items())
            if subscription.session_id == session_id
        ]
        for websocket in recipients:
            try:
                await self._send(websocket, payload)
            except (WebSocketDisconnect, RuntimeError):
                self._remove(websocket)
            if unsubscribe:
                self._subscriptions.pop(websocket, None)

    async def _heartbeat_loop(self, websocket: WebSocket) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            try:
                await self._send(websocket, {"type": "heartbeat", "timestamp": int(time.time() * 1000)})
            except (WebSocketDisconnect, RuntimeError):
                return

    async def _send_api_error(self, websocket: WebSocket, error: Any, request_id: Any = None) -> None:
        await self._send_error(
            websocket,
            error.code,
            error.message,
            request_id=request_id,
            details=error.details,
        )

    async def _send_error(
        self,
        websocket: WebSocket,
        code: str,
        message: str,
        *,
        request_id: Any = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        await self._send(
            websocket,
            {
                "type": "error",
                "request_id": request_id,
                "error": {"code": code, "message": message, "details": details or {}},
            },
        )

    async def _send(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        lock = self._send_locks.setdefault(websocket, asyncio.Lock())
        async with lock:
            await websocket.send_json(payload)

    def _remove(self, websocket: WebSocket) -> None:
        self._subscriptions.pop(websocket, None)
        self._send_locks.pop(websocket, None)


def snapshot_payload(
    state: dict[str, Any],
    rewards: dict[str, Any] | None,
    channels: Iterable[str],
) -> dict[str, Any]:
    """Build the documented C-to-D push payload from manager responses."""
    selected = frozenset(channels)
    payload: dict[str, Any] = {
        "type": "simulation.state",
        "session_id": state["session_id"],
        "transition_id": state["transition_id"],
        "timestamp": state["timestamp"],
        "simulation_time": state["simulation_time"],
        "state_layout_version": state["state_layout_version"],
        "intersection_order": state["intersection_order"],
    }
    if "state" in selected:
        payload["state_vector"] = state["state_vector"]
        payload["intersections"] = state["intersections"]
        # The formal Unity client renders this auxiliary snapshot from the
        # identical TraCI tick as the 660-D state.  Keep it optional for
        # backward-compatible fake managers and non-Unity subscribers.
        if "visualization" in state:
            payload["visualization"] = state["visualization"]
    if "reward" in selected and rewards is not None:
        payload["reward_version"] = rewards["reward_version"]
        payload["rewards"] = rewards["rewards"]
        payload["global_reward"] = rewards["global_reward"]
    return payload
