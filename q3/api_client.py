from __future__ import annotations

import json
import socket
import sys
from dataclasses import dataclass
from itertools import count
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .logger import JsonlLogger
from .models import Point


class SimulatorError(RuntimeError):
    pass


class SimulatorTransportError(SimulatorError):
    pass


class SimulatorBusinessError(SimulatorError):
    def __init__(self, path: str, response: dict[str, Any]):
        super().__init__(f"{path} not accepted: {response}")
        self.path = path
        self.response = response


@dataclass
class RequestIdFactory:
    prefix: str = "q3"

    def __post_init__(self) -> None:
        self._counter = count(1)

    def next(self, action: str) -> str:
        return f"{self.prefix}-{action}-{next(self._counter):06d}"


class SimulatorClient:
    """Official HTTP+JSON simulator client.

    The simulator exposes only four actions: /enter, /measure, /clear, /exit.
    Movement and channel switching are implicit in /measure and /clear payloads.
    """

    def __init__(
        self,
        robot_id: str,
        base_url: str = "http://127.0.0.1:2026",
        arena_id: str = "default",
        timeout_s: float = 5.0,
        request_ids: RequestIdFactory | None = None,
        logger: JsonlLogger | None = None,
        run_logger: Any | None = None,
    ):
        self.robot_id = robot_id
        self.base_url = base_url.rstrip("/")
        self.arena_id = arena_id
        self.timeout_s = timeout_s
        self.request_ids = request_ids or RequestIdFactory()
        self.logger = logger or JsonlLogger(None)
        self.run_logger = run_logger
        self.last_virtual_time_s: float | None = None
        self.current_position = Point(0.0, 0.0)

    def _run_log(self, action: str, payload: dict[str, Any], response: dict[str, Any] | None = None, error: str | None = None) -> None:
        """Passive run-logger hook: failures here must never affect the policy."""
        if self.run_logger is None:
            return
        try:
            self.run_logger.record(action, payload, response, error=error)
        except Exception as exc:  # noqa: BLE001 - logging must never break the run
            print(f"[run_logger] warning: record failed: {exc}", file=sys.stderr)

    def _base_payload(self, request_id: str) -> dict[str, Any]:
        return {
            "arena_id": self.arena_id,
            "robot_id": self.robot_id,
            "request_id": request_id,
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self.logger.write("request", path=path, payload=payload)
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                status = response.status
                text = response.read().decode("utf-8")
        except HTTPError as exc:
            status = exc.code
            raw = exc.read()
            text = raw.decode("utf-8", errors="replace") if raw else ""
        except (URLError, TimeoutError, socket.timeout) as exc:
            self.logger.write("transport_error", path=path, error=repr(exc))
            self._run_log(path.strip("/"), payload, None, error=f"transport_error: {exc!r}")
            raise SimulatorTransportError(f"{path} connection failed: {exc}") from exc

        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            self.logger.write("bad_json", path=path, status=status, body=text)
            self._run_log(path.strip("/"), payload, None, error=f"bad_json: {exc!r}")
            raise SimulatorTransportError(f"{path} returned non-JSON body: {text!r}") from exc

        self.logger.write("response", path=path, http_status=status, response=data)
        self._run_log(path.strip("/"), payload, data)
        if status != 200:
            raise SimulatorTransportError(f"{path} HTTP {status}: {data}")
        if data.get("accepted") is not True:
            raise SimulatorBusinessError(path, data)
        if "virtual_time_s" in data:
            self.last_virtual_time_s = float(data["virtual_time_s"])
        return data

    def enter(self) -> dict[str, Any]:
        request_id = self.request_ids.next("enter")
        return self._post("/enter", self._base_payload(request_id))

    def measure(self, position: Point, channel: int) -> dict[str, Any]:
        request_id = self.request_ids.next("measure")
        payload = self._base_payload(request_id)
        payload["position"] = position.as_payload()
        payload["channel"] = int(channel)
        response = self._post("/measure", payload)
        result = response.get("measure_result")
        if result not in {"direction", "near", "no_signal"}:
            raise SimulatorTransportError(f"unexpected measure_result: {response}")
        if result == "direction" and "svd_deg" not in response:
            raise SimulatorTransportError(f"direction response missing svd_deg: {response}")
        self.current_position = position
        return response

    def clear(self, position: Point, channel: int) -> dict[str, Any]:
        request_id = self.request_ids.next("clear")
        payload = self._base_payload(request_id)
        payload["position"] = position.as_payload()
        payload["channel"] = int(channel)
        response = self._post("/clear", payload)
        result = response.get("clear_result")
        if result not in {"success", "no_target_in_range"}:
            raise SimulatorTransportError(f"unexpected clear_result: {response}")
        self.current_position = position
        return response

    def exit(self) -> dict[str, Any]:
        request_id = self.request_ids.next("exit")
        return self._post("/exit", self._base_payload(request_id))

