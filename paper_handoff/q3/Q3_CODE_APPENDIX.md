# Q3 Complete Code Appendix

This appendix is generated from the current Q3 final runner dependency closure. Each section contains the complete source; no historical policy is included.

## q3/__init__.py

Role: package marker loaded by the final import chain.

```python
"""Q3 omnidirectional jammer search and clearing package."""
```

## run_q3_final.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from q3.api_client import RequestIdFactory, SimulatorClient
from q3.logger import JsonlLogger
from q3.models import ChannelStatus
from q3.run_logger import RunLogger, print_run_summary
from q3.v6_policy import policy_v6_official


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean Q3 final runner: RARC, fixed n=8, official simulator API."
    )
    parser.add_argument("--robot-id", default=os.getenv("ROBOT_ID"))
    parser.add_argument("--base-url", default=os.getenv("SIM_BASE_URL", "http://127.0.0.1:2026"))
    parser.add_argument(
        "--case-id",
        default=None,
        help="Test case code shown by the simulator UI. The API normally does not return it.",
    )
    parser.add_argument(
        "--test-kind",
        choices=("practice", "formal"),
        default="practice",
        help="Only affects local log labels. Choose formal for the three official attempts.",
    )
    parser.add_argument("--log", default="logs/q3_final_api.jsonl")
    return parser.parse_args()


def prompt_missing_args(args: argparse.Namespace) -> None:
    try:
        if not args.robot_id:
            args.robot_id = input("请输入参赛队号(须与模拟器登录队号完全一致): ").strip()
        if not args.case_id:
            case_id = input("请输入测试案例编码(可先留空, 结束后从模拟器日志列表补记): ").strip()
            args.case_id = case_id or None
    except EOFError:
        print()


def main() -> int:
    args = parse_args()
    prompt_missing_args(args)

    if not args.robot_id:
        print("未提供参赛队号, 已退出。", file=sys.stderr)
        return 2

    api_logger = JsonlLogger(Path(args.log))
    run_logger = RunLogger(
        base_dir="logs/q3_final",
        mode=args.test_kind,
        strategy="RARC",
        problem=3,
        case_id=args.case_id,
    )
    client = SimulatorClient(
        robot_id=args.robot_id,
        base_url=args.base_url,
        request_ids=RequestIdFactory("q3-rarc"),
        logger=api_logger,
        run_logger=run_logger,
    )

    policy = policy_v6_official(client, n=8)
    cleared = sum(1 for track in policy.tracks.values() if track.status == ChannelStatus.CLEARED)
    print(f"Q3 final RARC run complete: {cleared} channels cleared.")
    print(f"API log: {Path(args.log).resolve()}")
    if run_logger.summary:
        print_run_summary(run_logger.summary)
        print("Table 1 fields:")
        print(f"  测试案例编码: {run_logger.summary.get('case_id') or 'N/A'}")
        print(f"  清除干扰源个数: {run_logger.summary.get('cleared_count')}")
        print(f"  平均定位清除时间: {run_logger.summary.get('avg_time_per_cleared_s')}")
        print(f"  程序运行时间: {run_logger.summary.get('program_real_time_s')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

```

## q3/api_client.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
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


```

## q3/geometry.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .models import Measurement, Point

EPS = 1e-9
BEARING_ERROR_DEG = 1.0
BEARING_QUANTIZATION_DEG = 0.005
DEFAULT_BEARING_ERROR_DEG = BEARING_ERROR_DEG + BEARING_QUANTIZATION_DEG


@dataclass(frozen=True)
class Circle:
    center: Point
    radius: float


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def regular_polygon(radius: float, sides: int = 128, center: Point = Point(0.0, 0.0)) -> list[Point]:
    return [
        Point(center.x + radius * math.cos(2.0 * math.pi * i / sides), center.y + radius * math.sin(2.0 * math.pi * i / sides))
        for i in range(sides)
    ]


def clip_halfplane(poly: list[Point], a: float, b: float, c: float) -> list[Point]:
    """Clip by a*x + b*y + c >= 0."""
    if not poly:
        return []
    out: list[Point] = []

    def value(p: Point) -> float:
        return a * p.x + b * p.y + c

    prev = poly[-1]
    prev_v = value(prev)
    prev_inside = prev_v >= -EPS
    for cur in poly:
        cur_v = value(cur)
        cur_inside = cur_v >= -EPS
        if cur_inside != prev_inside:
            denom = a * (cur.x - prev.x) + b * (cur.y - prev.y)
            if abs(denom) > EPS:
                t = -prev_v / denom
                out.append(Point(prev.x + t * (cur.x - prev.x), prev.y + t * (cur.y - prev.y)))
        if cur_inside:
            out.append(cur)
        prev, prev_v, prev_inside = cur, cur_v, cur_inside
    return out


def clip_circle_superset(poly: list[Point], center: Point, radius: float, sides: int = 96) -> list[Point]:
    """Clip by a circumscribed regular polygon containing the circle."""
    out = poly
    for i in range(sides):
        angle = 2.0 * math.pi * i / sides
        nx, ny = math.cos(angle), math.sin(angle)
        # n dot (p - center) <= radius  ->  -n dot p + n dot center + radius >= 0
        out = clip_halfplane(out, -nx, -ny, nx * center.x + ny * center.y + radius)
        if not out:
            return []
    return out


def clip_bearing_wedge(poly: list[Point], position: Point, bearing_deg: float, error_deg: float = DEFAULT_BEARING_ERROR_DEG) -> list[Point]:
    lower = math.radians(bearing_deg - error_deg)
    upper = math.radians(bearing_deg + error_deg)
    ux_l, uy_l = math.cos(lower), math.sin(lower)
    ux_u, uy_u = math.cos(upper), math.sin(upper)
    # cross(u_lower, p-position) >= 0
    out = clip_halfplane(poly, -uy_l, ux_l, uy_l * position.x - ux_l * position.y)
    # cross(u_upper, p-position) <= 0
    out = clip_halfplane(out, uy_u, -ux_u, -uy_u * position.x + ux_u * position.y)
    return out


def localization_region(
    measurements: list[Measurement],
    target_radius: float = 1800.0,
    receive_radius_upper: float = 1500.0,
    bearing_error_deg: float = DEFAULT_BEARING_ERROR_DEG,
    sides: int = 160,
) -> list[Point]:
    """Return a conservative superset of the ±1 degree intersection region."""
    start_radius = target_radius / math.cos(math.pi / sides)
    poly = regular_polygon(start_radius, sides=sides)
    poly = clip_circle_superset(poly, Point(0.0, 0.0), target_radius, sides=sides)
    for m in measurements:
        if m.result != "direction" or m.svd_deg is None:
            continue
        poly = clip_bearing_wedge(poly, m.position, m.svd_deg, error_deg=bearing_error_deg)
        if not poly:
            return []
        poly = clip_circle_superset(poly, m.position, receive_radius_upper, sides=96)
        if not poly:
            return []
    return poly


def polygon_centroid(poly: list[Point]) -> Point:
    if not poly:
        return Point(0.0, 0.0)
    area2 = 0.0
    cx = 0.0
    cy = 0.0
    for p, q in zip(poly, poly[1:] + poly[:1]):
        cross = p.x * q.y - q.x * p.y
        area2 += cross
        cx += (p.x + q.x) * cross
        cy += (p.y + q.y) * cross
    if abs(area2) < EPS:
        return Point(sum(p.x for p in poly) / len(poly), sum(p.y for p in poly) / len(poly))
    return Point(cx / (3.0 * area2), cy / (3.0 * area2))


def circle_from_two(a: Point, b: Point) -> Circle:
    return Circle(Point((a.x + b.x) / 2.0, (a.y + b.y) / 2.0), distance(a, b) / 2.0)


def circle_from_three(a: Point, b: Point, c: Point) -> Circle | None:
    d = 2.0 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
    if abs(d) < EPS:
        return None
    ux = (
        (a.x * a.x + a.y * a.y) * (b.y - c.y)
        + (b.x * b.x + b.y * b.y) * (c.y - a.y)
        + (c.x * c.x + c.y * c.y) * (a.y - b.y)
    ) / d
    uy = (
        (a.x * a.x + a.y * a.y) * (c.x - b.x)
        + (b.x * b.x + b.y * b.y) * (a.x - c.x)
        + (c.x * c.x + c.y * c.y) * (b.x - a.x)
    ) / d
    center = Point(ux, uy)
    return Circle(center, distance(center, a))


def contains(circle: Circle, point: Point, eps: float = 1e-6) -> bool:
    return distance(circle.center, point) <= circle.radius + eps


def minimum_enclosing_circle(points: list[Point]) -> Circle:
    if not points:
        return Circle(Point(0.0, 0.0), float("inf"))

    # Deterministic incremental MEC. This is mathematically the same boundary
    # construction as the cubic fallback, but avoids pathological slowdowns when
    # clipping creates hundreds of polygon vertices during offline evaluation.
    ordered = list(points)
    random.Random(0).shuffle(ordered)
    best = Circle(ordered[0], 0.0)
    for i, p in enumerate(ordered):
        if contains(best, p):
            continue
        best = Circle(p, 0.0)
        for j, q in enumerate(ordered[:i]):
            if contains(best, q):
                continue
            best = circle_from_two(p, q)
            for r in ordered[:j]:
                if contains(best, r):
                    continue
                c = circle_from_three(p, q, r)
                if c is not None:
                    best = c
    if all(contains(best, p) for p in ordered):
        return best
    # Fallback for numerical edge cases.
    center = polygon_centroid(ordered)
    return Circle(center, max(distance(center, p) for p in ordered))


def max_distance_to_vertices(point: Point, poly: list[Point]) -> float:
    return max((distance(point, p) for p in poly), default=0.0)

```

## q3/logger.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonlLogger:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **payload: Any) -> None:
        if not self.path:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


```

## q3/models.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def as_payload(self) -> dict[str, float]:
        return {"x": float(self.x), "y": float(self.y)}


@dataclass(frozen=True)
class Measurement:
    position: Point
    channel: int
    result: str
    svd_deg: float | None
    virtual_time_s: float | None = None


class ChannelStatus(str, Enum):
    UNKNOWN = "unknown"
    FOUND = "found"
    CLEARED = "cleared"
    ABSENT = "absent"


@dataclass
class SourceTrack:
    channel: int
    status: ChannelStatus = ChannelStatus.UNKNOWN
    measurements: list[Measurement] = field(default_factory=list)
    clear_position: Point | None = None
    clear_response: dict[str, Any] | None = None
    localization_attempts: int = 0
    localization_cache_key: tuple[tuple[float, float, float | None], ...] | None = field(default=None, repr=False)
    localization_region_cache: Any | None = field(default=None, repr=False)
    localization_circle_cache: Any | None = field(default=None, repr=False)

    @property
    def direction_measurements(self) -> list[Measurement]:
        return [m for m in self.measurements if m.result == "direction"]

    def add_measurement(self, measurement: Measurement) -> None:
        self.measurements.append(measurement)
        self.localization_cache_key = None
        self.localization_region_cache = None
        self.localization_circle_cache = None
        if self.status == ChannelStatus.UNKNOWN:
            self.status = ChannelStatus.FOUND

```

## q3/offline_policy.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .api_client import SimulatorTransportError
from .geometry import (
    Circle,
    distance,
    localization_region,
    max_distance_to_vertices,
    minimum_enclosing_circle,
    polygon_centroid,
)
from .logger import JsonlLogger
from .models import ChannelStatus, Measurement, Point, SourceTrack
from .planner import Q3BaselinePlanner, Q3Config
from .routing import optimize_open_route as optimize_dynamic_open_route


ARENA_RADIUS_M = 1800.0
GUARANTEED_RECEIVE_RADIUS_M = 1000.0


def theoretical_outer_radius(n: int) -> float:
    radicand = GUARANTEED_RECEIVE_RADIUS_M**2 - (ARENA_RADIUS_M * math.sin(math.pi / n)) ** 2
    if n < 3 or radicand < 0.0:
        raise ValueError(f"n={n} does not admit guaranteed 1000m ring coverage")
    return ARENA_RADIUS_M * math.cos(math.pi / n) - math.sqrt(radicand)


def theoretical_route_length(n: int) -> float:
    a_n = theoretical_outer_radius(n)
    return a_n + (n - 1) * 2.0 * a_n * math.sin(math.pi / n)


THEORETICAL_HEX_RADIUS_M = theoretical_outer_radius(6)


class OfflineRunnerClient:
    """Adapter from offline_sim EpisodeRunner to the Q3 planner client shape."""

    def __init__(self, runner: Any):
        if hasattr(runner, "case"):
            raise SimulatorTransportError("policy runner exposes ground truth case; use PolicyRunnerProxy")
        self.runner = runner
        self.current_position = Point(0.0, 0.0)
        self.last_virtual_time_s: float | None = None

    def _accepted_response(self, response: dict | None, action: str) -> dict:
        if response is None:
            raise SimulatorTransportError(f"offline runner returned None during {action}")
        if "virtual_time_s" in response:
            self.last_virtual_time_s = float(response["virtual_time_s"])
        return response

    def enter(self) -> dict:
        response = self._accepted_response(self.runner.enter(), "enter")
        self.current_position = Point(0.0, 0.0)
        return response

    def measure(self, position: Point, channel: int) -> dict:
        response = self._accepted_response(self.runner.measure(position.x, position.y, int(channel)), "measure")
        result = response.get("measure_result")
        if result not in {"direction", "near", "no_signal"}:
            raise SimulatorTransportError(f"unexpected offline measure_result: {response}")
        if result == "direction" and "svd_deg" not in response:
            raise SimulatorTransportError(f"offline direction response missing svd_deg: {response}")
        self.current_position = position
        return response

    def clear(self, position: Point, channel: int) -> dict:
        response = self._accepted_response(self.runner.clear(position.x, position.y, int(channel)), "clear")
        result = response.get("clear_result")
        if result not in {"success", "no_target_in_range"}:
            raise SimulatorTransportError(f"unexpected offline clear_result: {response}")
        self.current_position = position
        return response

    def exit(self) -> dict:
        return self._accepted_response(self.runner.exit(), "exit")


def policy_v0(runner: Any, n: int = 6) -> None:
    """Q3 V0 policy for offline_sim: deterministic 7-point coverage + set localization."""
    client = OfflineRunnerClient(runner)
    radius = theoretical_outer_radius(n)
    planner = Q3BaselinePlanner(
        client,
        logger=JsonlLogger(None),
        config=Q3Config(
            search_radius=radius,
            search_points_n=n,
            clear_radius=20.0,
            clear_safety_radius=20.0,
            max_localization_measures=8,
            localize_on_detection=False,
            scan_found_at_search_points=False,
        ),
    )
    planner.run()


def policy_v1(runner: Any, n: int = 6) -> None:
    """V1: reuse later seven-point search locations as zero-movement localization points."""
    client = OfflineRunnerClient(runner)
    radius = theoretical_outer_radius(n)
    planner = Q3BaselinePlanner(
        client,
        logger=JsonlLogger(None),
        config=Q3Config(
            search_radius=radius,
            search_points_n=n,
            clear_radius=20.0,
            clear_safety_radius=20.0,
            max_localization_measures=8,
            localize_on_detection=False,
            scan_found_at_search_points=True,
        ),
    )
    planner.run()


@dataclass
class Task:
    kind: str
    channel: int
    point: Point
    search_index: int | None = None


class RouteOptimizedPolicy:
    def __init__(self, runner: Any, n: int = 6, dynamic_insert_clear: bool = False):
        self.client = OfflineRunnerClient(runner)
        self.tracks = {ch: SourceTrack(ch) for ch in range(1, 21)}
        self.n = n
        self.search_radius = theoretical_outer_radius(n)
        self.search_points = Q3BaselinePlanner.make_search_points(self.search_radius, n)
        self.dynamic_insert_clear = dynamic_insert_clear
        self.max_rounds = 8
        self.insert_delta_limit_m = self.search_radius * 0.2

    def run(self) -> None:
        self.client.enter()
        try:
            self.run_search_route()
            for track in self.tracks.values():
                if track.status == ChannelStatus.UNKNOWN:
                    track.status = ChannelStatus.ABSENT
            self.resolve_remaining_tasks()
        finally:
            self.client.exit()

    def run_search_route(self) -> None:
        for idx, point in enumerate(self.search_points):
            for channel in self.channels_to_scan(idx):
                self.measure_channel(point, channel)
            if self.dynamic_insert_clear:
                self.try_insert_clear_before_next(idx)

    def channels_to_scan(self, search_index: int) -> list[int]:
        channels = [
            ch
            for ch, track in self.tracks.items()
            if (
                track.status == ChannelStatus.UNKNOWN
                and self.discovered_count() < 16
            )
            or (
                track.status == ChannelStatus.FOUND
                and self.found_scan_has_value(track, self.search_points[search_index])
            )
        ]
        if search_index % 2 == 1:
            channels.reverse()
        return channels

    def discovered_count(self) -> int:
        return sum(1 for track in self.tracks.values() if track.status in {ChannelStatus.FOUND, ChannelStatus.CLEARED})

    def found_scan_has_value(self, track: SourceTrack, point: Point) -> bool:
        if track.status != ChannelStatus.FOUND:
            return False
        if any(distance(point, m.position) < 10.0 for m in track.direction_measurements):
            return False
        region, circle = self.localization_state(track)
        if circle is not None and circle.radius <= 20.0:
            return False
        if not region:
            return False
        if max_distance_to_vertices(point, region) > 995.0:
            return False
        center = circle.center if circle is not None else polygon_centroid(region)
        return Q3BaselinePlanner.crossing_quality(track, point, center) >= 0.2

    def measure_channel(self, point: Point, channel: int) -> None:
        track = self.tracks[channel]
        if track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT}:
            return
        response = self.client.measure(point, channel)
        result = response["measure_result"]
        svd = float(response["svd_deg"]) if result == "direction" else None
        if result == "no_signal":
            return
        measurement = Measurement(point, channel, result, svd, float(response["virtual_time_s"]))
        track.add_measurement(measurement)
        if result == "near":
            self.clear_track(track, point)

    def clear_track(self, track: SourceTrack, point: Point) -> bool:
        if track.status == ChannelStatus.CLEARED:
            return True
        response = self.client.clear(point, track.channel)
        track.clear_response = response
        if response["clear_result"] == "success":
            track.status = ChannelStatus.CLEARED
            track.clear_position = point
            return True
        return False

    def try_insert_clear_before_next(self, search_index: int) -> None:
        if search_index + 1 >= len(self.search_points):
            return
        current = self.client.current_position
        nxt = self.search_points[search_index + 1]
        while True:
            candidates = self.ready_clear_tasks()
            best: Task | None = None
            best_delta = float("inf")
            direct = distance(current, nxt)
            for task in candidates:
                delta = distance(current, task.point) + distance(task.point, nxt) - direct
                if delta < best_delta:
                    best_delta = delta
                    best = task
            if best is None or best_delta > self.insert_delta_limit_m:
                return
            self.clear_track(self.tracks[best.channel], best.point)
            current = self.client.current_position

    def resolve_remaining_tasks(self) -> None:
        for _ in range(self.max_rounds):
            tasks = self.build_tasks()
            if not tasks:
                return
            ordered = optimize_open_route(self.client.current_position, tasks)
            for task in ordered:
                track = self.tracks[task.channel]
                if track.status == ChannelStatus.CLEARED:
                    continue
                if task.kind == "clear":
                    self.clear_track(track, task.point)
                else:
                    self.measure_channel(task.point, task.channel)
            if all(t.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT, ChannelStatus.UNKNOWN} for t in self.tracks.values()):
                return

    def build_tasks(self) -> list[Task]:
        tasks = self.ready_clear_tasks()
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND:
                continue
            if any(task.channel == track.channel and task.kind == "clear" for task in tasks):
                continue
            candidate = self.localization_candidate(track)
            if candidate is not None:
                tasks.append(Task("measure", track.channel, candidate))
        return tasks

    def ready_clear_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND:
                continue
            circle = self.localization_circle(track)
            if circle is not None and circle.radius <= 20.0:
                tasks.append(Task("clear", track.channel, circle.center))
        return tasks

    @staticmethod
    def localization_state(track: SourceTrack) -> tuple[list[Point], Circle | None]:
        measurements = track.direction_measurements
        key = tuple((m.position.x, m.position.y, m.svd_deg) for m in measurements)
        if track.localization_cache_key == key:
            return track.localization_region_cache or [], track.localization_circle_cache
        region = localization_region(measurements) if measurements else []
        circle = minimum_enclosing_circle(region) if region else None
        track.localization_cache_key = key
        track.localization_region_cache = region
        track.localization_circle_cache = circle
        return region, circle

    @staticmethod
    def localization_circle(track: SourceTrack) -> Circle | None:
        return RouteOptimizedPolicy.localization_state(track)[1]

    def localization_candidate(self, track: SourceTrack) -> Point | None:
        region, circle = self.localization_state(track)
        if not region or circle is None:
            return None
        center = circle.center if math.isfinite(circle.radius) else polygon_centroid(region)
        offsets = [0.0, 250.0, 500.0, 750.0, 950.0]
        angles = [math.radians(15.0 * k) for k in range(24)]
        candidates: list[Point] = []
        for radius in offsets:
            if radius == 0.0:
                candidates.append(center)
            else:
                candidates.extend(Point(center.x + radius * math.cos(a), center.y + radius * math.sin(a)) for a in angles)

        best_point: Point | None = None
        best_score = -float("inf")
        current = self.client.current_position
        for point in candidates:
            if abs(point.x) > 2_000_000 or abs(point.y) > 2_000_000:
                continue
            if max_distance_to_vertices(point, region) > 995.0:
                continue
            quality = Q3BaselinePlanner.crossing_quality(track, point, center)
            move_penalty = distance(current, point) / 5000.0
            repeat_penalty = 1.0 if any(distance(point, m.position) < 10.0 for m in track.direction_measurements) else 0.0
            score = quality - move_penalty - repeat_penalty
            if score > best_score:
                best_score = score
                best_point = point
        return best_point or center


def route_length(start: Point, tasks: list[Task]) -> float:
    total = 0.0
    current = start
    for task in tasks:
        total += distance(current, task.point)
        current = task.point
    return total


def nearest_neighbor_route(start: Point, tasks: list[Task]) -> list[Task]:
    remaining = list(tasks)
    ordered: list[Task] = []
    current = start
    while remaining:
        idx = min(range(len(remaining)), key=lambda i: distance(current, remaining[i].point))
        task = remaining.pop(idx)
        ordered.append(task)
        current = task.point
    return ordered


def two_opt_open(start: Point, tasks: list[Task]) -> list[Task]:
    ordered = list(tasks)
    improved = True
    while improved:
        improved = False
        best_len = route_length(start, ordered)
        for i in range(len(ordered) - 1):
            for j in range(i + 2, len(ordered) + 1):
                candidate = ordered[:i] + list(reversed(ordered[i:j])) + ordered[j:]
                cand_len = route_length(start, candidate)
                if cand_len + 1e-6 < best_len:
                    ordered = candidate
                    best_len = cand_len
                    improved = True
                    break
            if improved:
                break
    return ordered


def optimize_open_route(start: Point, tasks: list[Task]) -> list[Task]:
    if len(tasks) <= 2:
        return nearest_neighbor_route(start, tasks)
    return two_opt_open(start, nearest_neighbor_route(start, tasks))


def policy_v2(runner: Any, n: int = 6) -> None:
    """V2: route all post-search localization and clear tasks with nearest-neighbor + 2-opt."""
    RouteOptimizedPolicy(runner, n=n, dynamic_insert_clear=False).run()


def policy_v3(runner: Any, n: int = 6) -> None:
    """V3: V2 plus low-detour clear insertion during the seven-point route."""
    RouteOptimizedPolicy(runner, n=n, dynamic_insert_clear=True).run()


class DynamicRoutingPolicy(RouteOptimizedPolicy):
    """V4: rolling online routing over current SEARCH/MEASURE/CLEAR tasks."""

    def __init__(self, runner: Any, n: int = 8):
        super().__init__(runner, n=n, dynamic_insert_clear=False)
        self.remaining_search_indices = set(range(len(self.search_points)))
        self.max_steps = 1000

    def run(self) -> None:
        self.client.enter()
        try:
            for _ in range(self.max_steps):
                self.update_unknown_state()
                tasks = self.build_dynamic_tasks()
                if not tasks:
                    return
                next_task = optimize_dynamic_open_route(self.client.current_position, tasks)[0]
                self.execute_task(next_task)
                if self.done():
                    return
        finally:
            self.client.exit()

    def done(self) -> bool:
        return all(track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT} for track in self.tracks.values())

    def update_unknown_state(self) -> None:
        if self.discovered_count() >= 16:
            self.remaining_search_indices.clear()
        if not self.remaining_search_indices:
            for track in self.tracks.values():
                if track.status == ChannelStatus.UNKNOWN:
                    track.status = ChannelStatus.ABSENT

    def build_dynamic_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        if self.discovered_count() < 16:
            for idx in sorted(self.remaining_search_indices):
                point = self.search_points[idx]
                if self.channels_to_scan_search_point(idx):
                    tasks.append(Task("search", 0, point, search_index=idx))

        tasks.extend(self.ready_clear_tasks())
        clear_channels = {task.channel for task in tasks if task.kind == "clear"}
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND or track.channel in clear_channels:
                continue
            candidate = self.localization_candidate(track)
            if candidate is not None:
                tasks.append(Task("measure", track.channel, candidate))
        return tasks

    def channels_to_scan_search_point(self, search_index: int) -> list[int]:
        point = self.search_points[search_index]
        channels = []
        for ch, track in self.tracks.items():
            if track.status == ChannelStatus.UNKNOWN and self.discovered_count() < 16:
                channels.append(ch)
            elif track.status == ChannelStatus.FOUND and self.found_scan_has_value(track, point):
                channels.append(ch)
        if search_index % 2 == 1:
            channels.reverse()
        return channels

    def execute_task(self, task: Task) -> None:
        if task.kind == "search":
            if task.search_index is None:
                return
            self.execute_search_task(task.search_index)
            return
        track = self.tracks[task.channel]
        if track.status == ChannelStatus.CLEARED:
            return
        if task.kind == "clear":
            self.clear_track(track, task.point)
        elif task.kind == "measure":
            self.measure_channel(task.point, task.channel)

    def execute_search_task(self, search_index: int) -> None:
        point = self.search_points[search_index]
        for channel in self.channels_to_scan_search_point(search_index):
            track = self.tracks[channel]
            if track.status == ChannelStatus.UNKNOWN and self.discovered_count() >= 16:
                continue
            if track.status in {ChannelStatus.CLEARED, ChannelStatus.ABSENT}:
                continue
            self.measure_channel(point, channel)
        self.remaining_search_indices.discard(search_index)


def policy_v4(runner: Any, n: int = 8) -> None:
    """V4: rolling online routing over SEARCH/MEASURE/CLEAR tasks."""
    DynamicRoutingPolicy(runner, n=n).run()


class OfficialClientRunnerAdapter:
    """Adapt an official SimulatorClient to the offline episode-runner call shape.

    Lets DynamicRoutingPolicy (V4) run unchanged against the official HTTP
    simulator; the client keeps its own request logging and response validation.
    """

    def __init__(self, client: Any):
        if hasattr(client, "case"):
            raise SimulatorTransportError("official client must not expose ground truth case")
        self._client = client

    def enter(self) -> dict:
        return self._client.enter()

    def measure(self, x: float, y: float, channel: int) -> dict:
        return self._client.measure(Point(x, y), int(channel))

    def clear(self, x: float, y: float, channel: int) -> dict:
        return self._client.clear(Point(x, y), int(channel))

    def exit(self) -> dict:
        return self._client.exit()


def policy_v4_official(client: Any, n: int = 8) -> DynamicRoutingPolicy:
    """Run V4 rolling dynamic routing against an official SimulatorClient.

    The caller is responsible for the practice confirmation gate; this function
    performs enter/exit itself, mirroring the offline entry points.
    """
    policy = DynamicRoutingPolicy(OfficialClientRunnerAdapter(client), n=n)
    policy.run()
    return policy

```

## q3/planner.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .api_client import SimulatorClient, SimulatorError
from .geometry import (
    Circle,
    distance,
    localization_region,
    max_distance_to_vertices,
    minimum_enclosing_circle,
    polygon_centroid,
)
from .logger import JsonlLogger
from .models import ChannelStatus, Measurement, Point, SourceTrack


@dataclass
class Q3Config:
    search_radius: float = 1150.0
    search_points_n: int = 6
    target_radius: float = 1800.0
    guaranteed_receive_radius: float = 1000.0
    clear_radius: float = 20.0
    clear_safety_radius: float = 19.5
    max_localization_measures: int = 8
    localize_on_detection: bool = True
    scan_found_at_search_points: bool = False


class Q3BaselinePlanner:
    def __init__(self, client: SimulatorClient, logger: JsonlLogger | None = None, config: Q3Config | None = None):
        self.client = client
        self.logger = logger or JsonlLogger(None)
        self.config = config or Q3Config()
        self.channels = {ch: SourceTrack(ch) for ch in range(1, 21)}
        self.search_points = self.make_search_points(self.config.search_radius, self.config.search_points_n)

    @staticmethod
    def make_search_points(radius: float, n: int = 6) -> list[Point]:
        points = [Point(0.0, 0.0)]
        for k in range(n):
            angle = 2.0 * math.pi * k / n
            points.append(Point(radius * math.cos(angle), radius * math.sin(angle)))
        return points

    def run(self) -> dict[str, Any]:
        summary: dict[str, Any] = {"cleared": 0, "absent": 0, "found_not_cleared": []}
        enter_response = self.client.enter()
        self.logger.write("enter_ok", response=enter_response)

        try:
            for idx, point in enumerate(self.search_points):
                self.logger.write("search_point_start", index=idx, point=point.as_payload())
                for ch in self.channels_to_scan_at_search_point(idx):
                    self.scan_channel_at(point, ch)
                self.logger.write("search_point_done", index=idx)

            for track in self.channels.values():
                if track.status == ChannelStatus.FOUND:
                    self.localize_and_clear(track)

            for track in self.channels.values():
                if track.status == ChannelStatus.UNKNOWN:
                    track.status = ChannelStatus.ABSENT
        finally:
            try:
                exit_response = self.client.exit()
                self.logger.write("exit_ok", response=exit_response)
            except SimulatorError as exc:
                self.logger.write("exit_failed", error=repr(exc))

        summary["cleared"] = sum(1 for t in self.channels.values() if t.status == ChannelStatus.CLEARED)
        summary["absent"] = sum(1 for t in self.channels.values() if t.status == ChannelStatus.ABSENT)
        summary["found_not_cleared"] = [t.channel for t in self.channels.values() if t.status == ChannelStatus.FOUND]
        summary["virtual_time_s"] = self.client.last_virtual_time_s
        self.logger.write("summary", summary=summary)
        return summary

    def channels_to_scan_at_search_point(self, search_index: int) -> list[int]:
        channels = [
            ch
            for ch, track in self.channels.items()
            if (
                track.status == ChannelStatus.UNKNOWN
                and self.discovered_count() < 16
            )
            or (
                self.config.scan_found_at_search_points
                and track.status == ChannelStatus.FOUND
                and self.found_scan_has_value(track, self.search_points[search_index])
            )
        ]
        if search_index % 2 == 1:
            channels.reverse()
        return channels

    def discovered_count(self) -> int:
        return sum(1 for track in self.channels.values() if track.status in {ChannelStatus.FOUND, ChannelStatus.CLEARED})

    def found_scan_has_value(self, track: SourceTrack, point: Point) -> bool:
        if track.status != ChannelStatus.FOUND:
            return False
        if any(distance(point, m.position) < 10.0 for m in track.direction_measurements):
            return False
        region, circle = self.localization_state(track)
        if not region or circle is None:
            return False
        if circle.radius <= self.config.clear_radius:
            return False
        if max_distance_to_vertices(point, region) > self.config.guaranteed_receive_radius - 5.0:
            return False
        return self.crossing_quality(track, point, circle.center) >= 0.2

    def localization_state(self, track: SourceTrack) -> tuple[list[Point], Circle | None]:
        measurements = track.direction_measurements
        key = tuple((m.position.x, m.position.y, m.svd_deg) for m in measurements)
        if track.localization_cache_key == key:
            return track.localization_region_cache or [], track.localization_circle_cache
        region = localization_region(measurements, target_radius=self.config.target_radius) if measurements else []
        circle = minimum_enclosing_circle(region) if region else None
        track.localization_cache_key = key
        track.localization_region_cache = region
        track.localization_circle_cache = circle
        return region, circle

    def scan_channel_at(self, point: Point, channel: int) -> None:
        track = self.channels[channel]
        if track.status == ChannelStatus.CLEARED or track.status == ChannelStatus.ABSENT:
            return
        if track.status == ChannelStatus.FOUND and not self.config.scan_found_at_search_points:
            return
        if track.status not in {ChannelStatus.UNKNOWN, ChannelStatus.FOUND}:
            return
        response = self.client.measure(point, channel)
        result = response["measure_result"]
        svd = float(response["svd_deg"]) if result == "direction" else None
        measurement = Measurement(point, channel, result, svd, float(response["virtual_time_s"]))
        self.logger.write("measure_parsed", channel=channel, point=point.as_payload(), result=result, svd_deg=svd)

        if result == "no_signal":
            return
        if result == "near":
            track.add_measurement(measurement)
            self.try_clear(track, point, reason="near")
            return

        track.add_measurement(measurement)
        if self.config.localize_on_detection:
            self.localize_and_clear(track)

    def try_clear(self, track: SourceTrack, position: Point, reason: str) -> bool:
        response = self.client.clear(position, track.channel)
        self.logger.write("clear_parsed", channel=track.channel, point=position.as_payload(), reason=reason, result=response["clear_result"])
        track.clear_response = response
        if response["clear_result"] == "success":
            track.status = ChannelStatus.CLEARED
            track.clear_position = position
            return True
        return False

    def localize_and_clear(self, track: SourceTrack) -> bool:
        if track.status == ChannelStatus.CLEARED:
            return True

        while track.localization_attempts < self.config.max_localization_measures:
            track.localization_attempts += 1
            region, circle = self.localization_state(track)
            if not region or circle is None:
                self.logger.write("localization_empty_region", channel=track.channel)
                return False

            self.logger.write(
                "localization_region",
                channel=track.channel,
                vertices=len(region),
                center=circle.center.as_payload(),
                radius=circle.radius,
            )

            if circle.radius <= self.config.clear_safety_radius:
                if self.try_clear(track, circle.center, reason="mec_radius"):
                    return True
                self.logger.write("clear_failed_continue_localizing", channel=track.channel, point=circle.center.as_payload(), radius=circle.radius)
                if self.measure_for_localization(track, circle.center, event="after_clear_failed_measure"):
                    return True
                continue

            next_point = self.choose_localization_point(track, region, circle)
            if self.measure_for_localization(track, next_point, event="local_measure_parsed"):
                return True

        region, circle = self.localization_state(track)
        if region and circle is not None and circle.radius <= self.config.clear_radius:
            return self.try_clear(track, circle.center, reason="final_radius")
        self.logger.write("localization_gave_up", channel=track.channel)
        return False

    def measure_for_localization(self, track: SourceTrack, point: Point, event: str) -> bool:
        response = self.client.measure(point, track.channel)
        result = response["measure_result"]
        svd = float(response["svd_deg"]) if result == "direction" else None
        measurement = Measurement(point, track.channel, result, svd, float(response["virtual_time_s"]))
        self.logger.write(event, channel=track.channel, point=point.as_payload(), result=result, svd_deg=svd)

        if result == "near":
            track.add_measurement(measurement)
            return self.try_clear(track, point, reason="near_local")
        if result == "direction":
            track.add_measurement(measurement)
            return False

        # For Q3 this should be rare if the candidate was chosen inside the guaranteed receive envelope.
        self.logger.write("local_measure_no_signal", channel=track.channel, point=point.as_payload())
        return False

    def choose_localization_point(self, track: SourceTrack, region: list[Point], circle: Circle) -> Point:
        center = circle.center if math.isfinite(circle.radius) else polygon_centroid(region)
        offsets = [0.0, 250.0, 500.0, 750.0, 950.0]
        angles = [math.radians(15.0 * k) for k in range(24)]
        candidates: list[Point] = []
        for r in offsets:
            if r == 0.0:
                candidates.append(center)
            else:
                candidates.extend(Point(center.x + r * math.cos(a), center.y + r * math.sin(a)) for a in angles)

        best_point = center
        best_score = -float("inf")
        for p in candidates:
            if abs(p.x) > 2_000_000 or abs(p.y) > 2_000_000:
                continue
            # If all vertices are within 1000 m, every possible source in this convex region is detectable.
            if max_distance_to_vertices(p, region) > self.config.guaranteed_receive_radius - 5.0:
                continue
            quality = self.crossing_quality(track, p, center)
            move_penalty = distance(self.client.current_position, p) / 5000.0
            repeat_penalty = 1.0 if any(distance(p, m.position) < 10.0 for m in track.direction_measurements) else 0.0
            score = quality - move_penalty - repeat_penalty
            if score > best_score:
                best_score = score
                best_point = p
        self.logger.write("localization_candidate", channel=track.channel, point=best_point.as_payload(), score=best_score)
        return best_point

    @staticmethod
    def crossing_quality(track: SourceTrack, candidate: Point, estimated_source: Point) -> float:
        vx = estimated_source.x - candidate.x
        vy = estimated_source.y - candidate.y
        norm_v = math.hypot(vx, vy)
        if norm_v < 1e-6:
            return 0.0
        best = 1.0
        for m in track.direction_measurements:
            ux = estimated_source.x - m.position.x
            uy = estimated_source.y - m.position.y
            norm_u = math.hypot(ux, uy)
            if norm_u < 1e-6:
                continue
            sin_angle = abs((ux * vy - uy * vx) / (norm_u * norm_v))
            best = min(best, sin_angle)
        return best

```

## q3/routing.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

from .geometry import distance
from .models import Point


class HasPoint(Protocol):
    point: Point


@dataclass(frozen=True)
class RouteSolution:
    order: list[int]
    length_m: float
    method: str
    exact: bool = False


def route_length_points(start: Point, points: Sequence[Point], order: Sequence[int] | None = None) -> float:
    if order is None:
        order = range(len(points))
    total = 0.0
    current = start
    for idx in order:
        total += distance(current, points[idx])
        current = points[idx]
    return total


def nearest_neighbor_order(start: Point, points: Sequence[Point]) -> list[int]:
    remaining = list(range(len(points)))
    ordered: list[int] = []
    current = start
    while remaining:
        best_pos = min(range(len(remaining)), key=lambda k: distance(current, points[remaining[k]]))
        idx = remaining.pop(best_pos)
        ordered.append(idx)
        current = points[idx]
    return ordered


def cheapest_insertion_order(start: Point, points: Sequence[Point]) -> list[int]:
    if not points:
        return []
    first = min(range(len(points)), key=lambda i: distance(start, points[i]))
    route = [first]
    remaining = [i for i in range(len(points)) if i != first]
    while remaining:
        best_idx = remaining[0]
        best_pos = len(route)
        best_delta = float("inf")
        for idx in remaining:
            for pos in range(len(route) + 1):
                prev_point = start if pos == 0 else points[route[pos - 1]]
                next_point = None if pos == len(route) else points[route[pos]]
                remove = 0.0 if next_point is None else distance(prev_point, next_point)
                add = distance(prev_point, points[idx])
                if next_point is not None:
                    add += distance(points[idx], next_point)
                delta = add - remove
                if delta < best_delta:
                    best_delta = delta
                    best_idx = idx
                    best_pos = pos
        route.insert(best_pos, best_idx)
        remaining.remove(best_idx)
    return route


def two_opt_order(start: Point, points: Sequence[Point], order: Sequence[int]) -> list[int]:
    route = list(order)
    if len(route) <= 2:
        return route

    def point_before(pos: int) -> Point:
        return start if pos == 0 else points[route[pos - 1]]

    improved = True
    while improved:
        improved = False
        for i in range(len(route) - 1):
            a = point_before(i)
            b = points[route[i]]
            for j in range(i + 1, len(route)):
                c = points[route[j]]
                d = None if j + 1 == len(route) else points[route[j + 1]]
                old = distance(a, b) + (0.0 if d is None else distance(c, d))
                new = distance(a, c) + (0.0 if d is None else distance(b, d))
                if new + 1e-6 < old:
                    route[i : j + 1] = reversed(route[i : j + 1])
                    improved = True
                    break
            if improved:
                break
    return route


def optimize_open_point_route(start: Point, points: Sequence[Point]) -> RouteSolution:
    if not points:
        return RouteSolution([], 0.0, "empty", exact=True)
    candidates = [("nearest+2opt", two_opt_order(start, points, nearest_neighbor_order(start, points)))]
    if len(points) <= 80:
        candidates.append(("cheapest-insertion+2opt", two_opt_order(start, points, cheapest_insertion_order(start, points))))
    method, order = min(candidates, key=lambda item: route_length_points(start, points, item[1]))
    return RouteSolution(order, route_length_points(start, points, order), method, exact=False)


def optimize_open_route(start: Point, items: Sequence[HasPoint]) -> list[HasPoint]:
    points = [item.point for item in items]
    solution = optimize_open_point_route(start, points)
    return [items[idx] for idx in solution.order]


def exact_open_route_length(start: Point, points: Sequence[Point], max_exact_points: int = 12) -> RouteSolution:
    n = len(points)
    if n == 0:
        return RouteSolution([], 0.0, "exact-dp", exact=True)
    if n > max_exact_points:
        approximate = optimize_open_point_route(start, points)
        return RouteSolution(approximate.order, approximate.length_m, approximate.method, exact=False)

    dp: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {}
    for i, point in enumerate(points):
        dp[(1 << i, i)] = (distance(start, point), (i,))

    for mask in range(1, 1 << n):
        for last in range(n):
            state = (mask, last)
            if state not in dp:
                continue
            base_len, base_order = dp[state]
            remain = ((1 << n) - 1) ^ mask
            bitset = remain
            while bitset:
                bit = bitset & -bitset
                nxt = bit.bit_length() - 1
                new_mask = mask | bit
                cand = base_len + distance(points[last], points[nxt])
                old = dp.get((new_mask, nxt))
                if old is None or cand < old[0]:
                    dp[(new_mask, nxt)] = (cand, base_order + (nxt,))
                bitset ^= bit

    full = (1 << n) - 1
    length, order_tuple = min((dp[(full, last)] for last in range(n) if (full, last) in dp), key=lambda item: item[0])
    return RouteSolution(list(order_tuple), length, "exact-dp", exact=True)

```

## q3/run_logger.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
"""Run-level logging and result persistence for official Q3 runs.

Design constraints (competition safety first):
- Records ONLY what the program observed through the official API
  (request payloads and responses). Never touches ground truth.
- Adds no API calls and never changes action ordering: the logger is a
  passive observer hooked into SimulatorClient._post.
- Append-only, flush-per-event so a mid-run crash keeps prior events.
- Any logging failure degrades to a stderr warning; it never raises into
  the policy and therefore never changes robot decisions.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SPEED_MPS = 5.0  # robot speed, same convention as offline_sim/engine.py

RUNS_SUMMARY_FIELDS = [
    "run_id",
    "problem",
    "mode",
    "strategy",
    "case_id",
    "source_count",
    "cleared_count",
    "clear_rate",
    "total_virtual_time_s",
    "avg_time_per_source_s",
    "avg_time_per_cleared_s",
    "total_movement_distance_m",
    "movement_time_s",
    "measure_count",
    "channel_switch_count",
    "clear_attempt_count",
    "clear_success_count",
    "clear_fail_count",
    "program_real_time_s",
    "program_wall_time_s",
]

TRAJECTORY_FIELDS = [
    "seq",
    "virtual_time_s",
    "action",
    "x",
    "y",
    "channel",
    "result_type",
    "direction_deg",
    "clear_success",
    "moved_distance_m",
    "cumulative_distance_m",
]

_CASE_ID_KEYS = ("case_id", "case_code", "test_case_id", "scenario_id", "case")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


class RunLogger:
    """Collects one official run into logs/<problem>/<run_id>/ plus a global CSV row."""

    def __init__(
        self,
        base_dir: Path | str = Path("logs/q3"),
        mode: str = "practice",
        strategy: str | None = None,
        problem: int = 3,
        case_id: str | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.mode = mode
        self.strategy = strategy
        self.problem = problem
        self.run_id: str | None = None
        self.run_dir: Path | None = None
        self.case_id: str | None = case_id
        self.summary: dict[str, Any] | None = None

        self._pending_events: list[dict[str, Any]] = []
        self._events_fh = None
        self._traj_fh = None
        self._traj_writer = None

        self._seq = 0
        self._start_wall = time.time()
        self._end_wall: float | None = None
        self._start_iso = _now_iso()
        self._end_iso: str | None = None
        self._enter_real_timestamp_ms: float | None = None
        self._exit_real_timestamp_ms: float | None = None

        self._last_position: tuple[float, float] | None = None
        self._current_channel = 1  # simulator powers up on channel 1
        self._cum_distance = 0.0
        self._last_virtual_time: float | None = None

        self._measure_count = 0
        self._direction_count = 0
        self._near_count = 0
        self._no_signal_count = 0
        self._channel_switch_count = 0
        self._clear_attempt = 0
        self._clear_success = 0
        self._clear_fail = 0

    # ------------------------------------------------------------------ utils
    def _warn(self, message: str) -> None:
        print(f"[run_logger] warning: {message}", file=sys.stderr)

    def _next_run_id(self, now: datetime) -> str:
        stamp = now.strftime("%Y%m%d_%H%M%S")
        pattern = re.compile(rf"^{now.strftime('%Y%m%d')}_\d{{6}}_{re.escape(self.mode)}_(\d{{3}})$")
        highest = 0
        if self.base_dir.is_dir():
            for entry in self.base_dir.iterdir():
                match = pattern.match(entry.name)
                if match and entry.is_dir():
                    highest = max(highest, int(match.group(1)))
        return f"{stamp}_{self.mode}_{highest + 1:03d}"

    # ------------------------------------------------------------- lifecycle
    def begin_run(self, enter_response: dict[str, Any]) -> None:
        """Create the run directory once /enter is accepted; flush buffered events."""
        if self.run_dir is not None:
            return
        now = datetime.now().astimezone()
        self.run_id = self._next_run_id(now)
        self.run_dir = self.base_dir / self.run_id
        if self.case_id is None:
            for key in _CASE_ID_KEYS:
                value = enter_response.get(key)
                if value not in (None, ""):
                    self.case_id = str(value)
                    break
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self._events_fh = (self.run_dir / "events.jsonl").open("a", encoding="utf-8")
            self._traj_fh = (self.run_dir / "trajectory.csv").open("a", encoding="utf-8", newline="")
            self._traj_writer = csv.writer(self._traj_fh)
            self._traj_writer.writerow(TRAJECTORY_FIELDS)
            self._traj_fh.flush()
        except OSError as exc:
            self._warn(f"cannot open run directory {self.run_dir}: {exc}")
            self._events_fh = None
            self._traj_fh = None
            self._traj_writer = None
        buffered, self._pending_events = self._pending_events, []
        for event in buffered:
            self._write_event(event)

    def finalize(self) -> dict[str, Any] | None:
        """Write summary.json and append the global runs_summary.csv row."""
        if self.summary is not None or self.run_dir is None:
            return self.summary
        self._end_wall = time.time()
        self._end_iso = _now_iso()
        cleared = self._clear_success
        total_virtual = self._last_virtual_time
        program_real_time = None
        if self._enter_real_timestamp_ms is not None and self._exit_real_timestamp_ms is not None:
            program_real_time = (self._exit_real_timestamp_ms - self._enter_real_timestamp_ms) / 1000.0
        summary: dict[str, Any] = {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "problem": self.problem,
            "mode": self.mode,
            "strategy": self.strategy,
            "case_id": self.case_id,
            "start_time": self._start_iso,
            "end_time": self._end_iso,
            "source_count": None,  # official API never reveals it; fill via update_run_metadata.py
            "cleared_count": cleared,
            "clear_rate": None,
            "total_virtual_time_s": total_virtual,
            "avg_time_per_source_s": None,
            "avg_time_per_cleared_s": (total_virtual / cleared) if cleared and total_virtual is not None else None,
            "total_movement_distance_m": self._cum_distance,
            "movement_time_s": self._cum_distance / SPEED_MPS,
            "measure_count": self._measure_count,
            "direction_count": self._direction_count,
            "near_count": self._near_count,
            "no_signal_count": self._no_signal_count,
            "channel_switch_count": self._channel_switch_count,
            "clear_attempt_count": self._clear_attempt,
            "clear_success_count": self._clear_success,
            "clear_fail_count": self._clear_fail,
            "enter_real_timestamp_ms": self._enter_real_timestamp_ms,
            "exit_real_timestamp_ms": self._exit_real_timestamp_ms,
            "program_real_time_s": program_real_time,
            "program_wall_time_s": (self._end_wall - self._start_wall),
        }
        self.summary = summary
        try:
            with (self.run_dir / "summary.json").open("w", encoding="utf-8") as fh:
                json.dump(summary, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._warn(f"cannot write summary.json: {exc}")
        self._append_runs_summary(summary)
        for fh in (self._events_fh, self._traj_fh):
            try:
                if fh:
                    fh.close()
            except OSError:
                pass
        self._events_fh = None
        self._traj_fh = None
        return summary

    def _append_runs_summary(self, summary: dict[str, Any]) -> None:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            target = self.base_dir / "runs_summary.csv"
            write_header = not target.exists() or target.stat().st_size == 0
            with target.open("a", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=RUNS_SUMMARY_FIELDS)
                if write_header:
                    writer.writeheader()
                writer.writerow({key: summary.get(key) for key in RUNS_SUMMARY_FIELDS})
                fh.flush()
        except OSError as exc:
            self._warn(f"cannot append runs_summary.csv: {exc}")

    # ------------------------------------------------------------ event hook
    def record(
        self,
        action: str,
        request: dict[str, Any] | None,
        response: dict[str, Any] | None,
        error: str | None = None,
    ) -> None:
        """Passive observer: called once per API call, right after the response."""
        self._seq += 1
        accepted = response.get("accepted") if isinstance(response, dict) else None
        position = None
        if isinstance(request, dict) and isinstance(request.get("position"), dict):
            raw = request["position"]
            position = [raw.get("x"), raw.get("y")]
        channel = request.get("channel") if isinstance(request, dict) else None
        virtual_time = response.get("virtual_time_s") if isinstance(response, dict) else None
        result_type = None
        direction_deg = None
        if isinstance(response, dict):
            result_type = response.get("measure_result") or response.get("clear_result")
            direction_deg = response.get("svd_deg")
        event = {
            "seq": self._seq,
            "wall_time": _now_iso(),
            "action": action,
            "request_id": request.get("request_id") if isinstance(request, dict) else None,
            "position": position,
            "channel": channel,
            "request": request,
            "response": response,
            "accepted": accepted,
            "result_type": result_type,
            "direction_deg": direction_deg,
            "virtual_time_s": virtual_time,
        }
        if error is not None:
            event["error"] = error

        if action == "enter" and accepted is True and self.run_dir is None:
            self._enter_real_timestamp_ms = _as_float(response.get("real_timestamp_ms") if isinstance(response, dict) else None)
            self.begin_run(response or {})
        elif action == "exit" and accepted is True:
            self._exit_real_timestamp_ms = _as_float(response.get("real_timestamp_ms") if isinstance(response, dict) else None)
        if self.run_dir is None:
            self._pending_events.append(event)
            return
        self._write_event(event)
        if accepted is True:
            self._observe(action, position, channel, result_type, direction_deg, virtual_time)
        if action == "exit":
            self.finalize()

    def _write_event(self, event: dict[str, Any]) -> None:
        if self._events_fh is None:
            return
        try:
            self._events_fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._events_fh.flush()
        except OSError as exc:
            self._warn(f"cannot append events.jsonl: {exc}")

    def _observe(
        self,
        action: str,
        position: list[Any] | None,
        channel: Any,
        result_type: Any,
        direction_deg: Any,
        virtual_time: Any,
    ) -> None:
        """Update counters/trajectory from what the API actually confirmed."""
        if virtual_time is not None:
            try:
                self._last_virtual_time = float(virtual_time)
            except (TypeError, ValueError):
                pass
        if action not in ("measure", "clear") or position is None:
            return
        try:
            x, y = float(position[0]), float(position[1])
            channel_int = int(channel) if channel is not None else None
        except (TypeError, ValueError, IndexError):
            return

        moved = 0.0
        if self._last_position is not None:
            moved = ((x - self._last_position[0]) ** 2 + (y - self._last_position[1]) ** 2) ** 0.5
        self._cum_distance += moved
        self._last_position = (x, y)

        clear_success: int | str = ""
        if action == "measure":
            self._measure_count += 1
            if result_type == "direction":
                self._direction_count += 1
            elif result_type == "near":
                self._near_count += 1
            elif result_type == "no_signal":
                self._no_signal_count += 1
            if channel_int is not None and channel_int != self._current_channel:
                self._channel_switch_count += 1
                self._current_channel = channel_int
        elif action == "clear":
            self._clear_attempt += 1
            if result_type == "success":
                self._clear_success += 1
                clear_success = 1
            else:
                self._clear_fail += 1
                clear_success = 0

        if self._traj_writer is None:
            return
        try:
            self._traj_writer.writerow(
                [
                    self._seq,
                    self._last_virtual_time,
                    action,
                    x,
                    y,
                    channel_int,
                    result_type,
                    direction_deg,
                    clear_success,
                    moved,
                    self._cum_distance,
                ]
            )
            self._traj_fh.flush()
        except OSError as exc:
            self._warn(f"cannot append trajectory.csv: {exc}")


def print_run_summary(summary: dict[str, Any]) -> None:
    """Terminal block required by the logging spec."""
    cleared = summary.get("cleared_count")
    source = summary.get("source_count")
    total_virtual = summary.get("total_virtual_time_s")
    avg = summary.get("avg_time_per_source_s")
    avg_cleared = summary.get("avg_time_per_cleared_s")
    lines = [
        f"================ Q{summary.get('problem', 3)} RUN SUMMARY ================",
        f"Run ID:          {summary.get('run_id')}",
        f"Mode:            {str(summary.get('mode')).upper()}",
        f"Strategy:        {summary.get('strategy') or 'N/A'}",
        f"Case ID:         {summary.get('case_id') or 'N/A'}",
        "",
        f"Cleared:         {cleared}",
        f"Source count:    {source if source is not None else 'N/A'}",
        f"Clear rate:      {format_percent(summary.get('clear_rate'))}",
        "",
        f"Virtual time:    {format_seconds(total_virtual)}",
        f"Avg/source:      {format_seconds_per(avg, 'source')}",
        f"Avg/cleared:     {format_seconds_per(avg_cleared, 'cleared source')}",
        f"Program runtime: {format_seconds(summary.get('program_real_time_s'))}",
        f"Local wall time: {format_seconds(summary.get('program_wall_time_s'))}",
        "",
        f"Movement:        {format_meters(summary.get('total_movement_distance_m'))}",
        f"Measures:        {summary.get('measure_count')}",
        f"Switches:        {summary.get('channel_switch_count')}",
        f"Clear failures:  {summary.get('clear_fail_count')}",
        "",
        "Logs saved to:",
        f"{summary.get('run_dir') or 'N/A'}/",
        "================================================",
    ]
    print("\n".join(lines))


def format_percent(value: Any) -> str:
    return "N/A" if value is None else f"{value * 100:.2f} %"


def format_seconds(value: Any) -> str:
    return "N/A" if value is None else f"{value:.3f} s"


def format_seconds_per(value: Any, denominator: str) -> str:
    return "N/A" if value is None else f"{value:.3f} s/{denominator}"


def format_meters(value: Any) -> str:
    return "N/A" if value is None else f"{value:.2f} m"


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

```

## q3/v5_policy.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from .geometry import distance, max_distance_to_vertices
from .models import ChannelStatus, Point, SourceTrack
from .offline_policy import DynamicRoutingPolicy, Task
from .v5_prediction import (
    CandidatePrediction,
    V5PredictionConfig,
    eligible_candidates,
    predict_candidate,
    sample_feasible_polygon,
)


def _finite_radius(track: SourceTrack, policy: DynamicRoutingPolicy) -> float | None:
    circle = policy.localization_circle(track)
    if circle is None or not math.isfinite(circle.radius):
        return None
    return circle.radius


class DiagnosticDynamicRoutingPolicy(DynamicRoutingPolicy):
    """V4 behavior with policy-visible source diagnostics only."""

    variant = "v4"

    def __init__(self, runner: Any, n: int = 8):
        super().__init__(runner, n=n)
        self._active_search_index: int | None = None
        self._wait_assignments: dict[int, int] = {}

    def emit(self, event: str, **payload: Any) -> None:
        recorder = getattr(self.client.runner, "record_policy_diagnostic", None)
        if recorder is not None:
            recorder({"event": event, "variant": self.variant, **payload})

    def execute_search_task(self, search_index: int) -> None:
        self._active_search_index = search_index
        try:
            super().execute_search_task(search_index)
        finally:
            self._active_search_index = None

    def measure_channel(self, point: Point, channel: int) -> None:
        track = self.tracks[channel]
        status_before = track.status
        position_before = self.client.current_position
        measurements_before = len(track.measurements)
        mec_before = _finite_radius(track, self) if status_before == ChannelStatus.FOUND else None
        waited_for_search = bool(
            self._active_search_index is not None
            and self._wait_assignments.get(channel) == self._active_search_index
        )

        super().measure_channel(point, channel)

        new_measurement = track.measurements[-1] if len(track.measurements) > measurements_before else None
        result = new_measurement.result if new_measurement is not None else "no_signal"
        measure_time = (
            new_measurement.virtual_time_s
            if new_measurement is not None and new_measurement.virtual_time_s is not None
            else self.client.last_virtual_time_s
        )
        if status_before == ChannelStatus.UNKNOWN and track.status in {ChannelStatus.FOUND, ChannelStatus.CLEARED}:
            self.emit(
                "first_found",
                channel=channel,
                time_s=measure_time,
                x=point.x,
                y=point.y,
                result=result,
            )
        if status_before != ChannelStatus.FOUND:
            return

        mec_after = 0.0 if result == "near" else _finite_radius(track, self)
        self.emit(
            "supplement_measure",
            channel=channel,
            time_s=measure_time,
            x=point.x,
            y=point.y,
            result=result,
            mec_before_m=mec_before,
            mec_after_m=mec_after,
            arrival_move_m=distance(position_before, point),
            at_mandatory_search=bool(self._active_search_index is not None),
            search_index=self._active_search_index,
            waited_for_search=waited_for_search,
            clearable_after=bool(result == "near" or (mec_after is not None and mec_after <= 20.0)),
        )

    def clear_track(self, track: SourceTrack, point: Point) -> bool:
        if track.status == ChannelStatus.CLEARED:
            return True
        position_before = self.client.current_position
        final_mec = _finite_radius(track, self)
        success = super().clear_track(track, point)
        self.emit(
            "clear",
            channel=track.channel,
            time_s=self.client.last_virtual_time_s,
            x=point.x,
            y=point.y,
            result="success" if success else "no_target_in_range",
            final_mec_m=final_mec,
            arrival_move_m=distance(position_before, point),
        )
        return success


class V5TaskGenerationPolicy(DiagnosticDynamicRoutingPolicy):
    """Change only FOUND-source MEASURE task generation; inherit V4 routing."""

    def __init__(
        self,
        runner: Any,
        n: int = 8,
        mode: str = "final",
        prediction_config: V5PredictionConfig | None = None,
    ):
        super().__init__(runner, n=n)
        if mode not in {"a", "b", "final"}:
            raise ValueError(f"unknown V5 mode: {mode}")
        self.mode = mode
        self.variant = f"v5{mode}"
        self.prediction_config = prediction_config or V5PredictionConfig()
        self._sample_cache: dict[tuple, list[Point]] = {}
        self._prediction_cache: dict[tuple, CandidatePrediction] = {}
        self._last_decision_key: dict[int, tuple] = {}

    @staticmethod
    def _track_key(track: SourceTrack) -> tuple:
        return tuple((m.position.x, m.position.y, m.svd_deg) for m in track.direction_measurements)

    def samples_for(self, track: SourceTrack, region: list[Point]) -> list[Point]:
        key = (track.channel, self._track_key(track))
        if key not in self._sample_cache:
            seed = (
                self.prediction_config.sample_seed
                + track.channel * 1009
                + len(track.direction_measurements) * 9176
            )
            self._sample_cache[key] = sample_feasible_polygon(
                region,
                self.prediction_config.sample_count,
                seed,
            )
        return self._sample_cache[key]

    def prediction(
        self,
        track: SourceTrack,
        region: list[Point],
        point: Point,
        mandatory_search_point: bool,
    ) -> CandidatePrediction:
        cache_key = (
            track.channel,
            self._track_key(track),
            round(point.x, 6),
            round(point.y, 6),
        )
        base = self._prediction_cache.get(cache_key)
        if base is None:
            base = predict_candidate(
                track,
                region,
                point,
                self.client.current_position,
                self.samples_for(track, region),
                self.prediction_config,
                mandatory_search_point=True,
            )
            self._prediction_cache[cache_key] = base
        move_time = 0.0 if mandatory_search_point else distance(self.client.current_position, point) / self.prediction_config.robot_speed_mps
        return replace(
            base,
            expected_total_incremental_time_s=(
                move_time
                + self.prediction_config.measure_time_s
                + base.expected_remaining_time_s
            ),
        )

    def dedicated_prediction(self, track: SourceTrack, region: list[Point], use_v5_candidates: bool) -> CandidatePrediction | None:
        v4_point = self.localization_candidate(track)
        if v4_point is None:
            return None
        points = [v4_point]
        if use_v5_candidates:
            circle = self.localization_circle(track)
            if circle is not None:
                points = eligible_candidates(
                    track,
                    region,
                    circle,
                    self.prediction_config,
                    extra_points=(v4_point,),
                )
        predictions = [self.prediction(track, region, point, False) for point in points]
        if self.mode in {"b", "final"}:
            return max(
                predictions,
                key=lambda item: (item.p_clear, -item.expected_total_incremental_time_s),
                default=None,
            )
        return min(predictions, key=lambda item: item.expected_total_incremental_time_s, default=None)

    def search_prediction(self, track: SourceTrack, region: list[Point]) -> tuple[int, CandidatePrediction] | None:
        candidates: list[tuple[int, CandidatePrediction]] = []
        for idx in sorted(self.remaining_search_indices):
            point = self.search_points[idx]
            if max_distance_to_vertices(point, region) > self.prediction_config.guaranteed_receive_distance_m:
                continue
            if any(distance(point, m.position) < self.prediction_config.repeat_distance_m for m in track.direction_measurements):
                continue
            candidates.append((idx, self.prediction(track, region, point, True)))
        return min(candidates, key=lambda item: item[1].expected_total_incremental_time_s, default=None)

    def measure_task_for(self, track: SourceTrack) -> Task | None:
        region, circle = self.localization_state(track)
        if not region or circle is None:
            return None

        use_v5_candidates = self.mode in {"b", "final"}
        dedicated = self.dedicated_prediction(track, region, use_v5_candidates)
        future_search = self.search_prediction(track, region) if self.mode in {"a", "final"} else None

        choose_wait = bool(
            future_search is not None
            and dedicated is not None
            and future_search[1].expected_total_incremental_time_s
            <= dedicated.expected_total_incremental_time_s
            and (
                self.mode == "a"
                or future_search[1].p_clear >= dedicated.p_clear
            )
        )
        if choose_wait:
            search_index, search_estimate = future_search
            self._wait_assignments[track.channel] = search_index
            selected_kind = "wait_search"
            selected = search_estimate
        else:
            selected_kind = "dedicated"
            selected = dedicated

        decision_key = (
            self._track_key(track),
            selected_kind,
            None if selected is None else round(selected.point.x, 6),
            None if selected is None else round(selected.point.y, 6),
        )
        if self._last_decision_key.get(track.channel) != decision_key:
            self._last_decision_key[track.channel] = decision_key
            self.emit(
                "measure_decision",
                channel=track.channel,
                mode=self.mode,
                selected_kind=selected_kind,
                selected_x=None if selected is None else selected.point.x,
                selected_y=None if selected is None else selected.point.y,
                selected_p_clear=None if selected is None else selected.p_clear,
                selected_expected_mec_m=None if selected is None else selected.expected_mec_after_m,
                selected_expected_total_s=None if selected is None else selected.expected_total_incremental_time_s,
                dedicated_p_clear=None if dedicated is None else dedicated.p_clear,
                dedicated_expected_total_s=None if dedicated is None else dedicated.expected_total_incremental_time_s,
                search_index=None if future_search is None else future_search[0],
                search_p_clear=None if future_search is None else future_search[1].p_clear,
                search_expected_total_s=None if future_search is None else future_search[1].expected_total_incremental_time_s,
            )

        if choose_wait or dedicated is None:
            return None
        return Task("measure", track.channel, dedicated.point)

    def build_dynamic_tasks(self) -> list[Task]:
        self._wait_assignments = {}
        tasks: list[Task] = []
        if self.discovered_count() < 16:
            for idx in sorted(self.remaining_search_indices):
                point = self.search_points[idx]
                if self.channels_to_scan_search_point(idx):
                    tasks.append(Task("search", 0, point, search_index=idx))

        tasks.extend(self.ready_clear_tasks())
        clear_channels = {task.channel for task in tasks if task.kind == "clear"}
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND or track.channel in clear_channels:
                continue
            task = self.measure_task_for(track)
            if task is not None:
                tasks.append(task)
        return tasks

    def channels_to_scan_search_point(self, search_index: int) -> list[int]:
        channels = set(super().channels_to_scan_search_point(search_index))
        channels.update(
            channel
            for channel, assigned_index in self._wait_assignments.items()
            if assigned_index == search_index and self.tracks[channel].status == ChannelStatus.FOUND
        )
        ordered = sorted(channels)
        if search_index % 2 == 1:
            ordered.reverse()
        return ordered


def policy_v4_diagnostic(runner: Any, n: int = 8) -> None:
    DiagnosticDynamicRoutingPolicy(runner, n=n).run()


def policy_v5a(runner: Any, n: int = 8) -> None:
    V5TaskGenerationPolicy(runner, n=n, mode="a").run()


def policy_v5b(runner: Any, n: int = 8) -> None:
    V5TaskGenerationPolicy(runner, n=n, mode="b").run()


def policy_v5_final(runner: Any, n: int = 8) -> None:
    V5TaskGenerationPolicy(runner, n=n, mode="final").run()

```

## q3/v5_prediction.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass

from .geometry import (
    Circle,
    clip_bearing_wedge,
    distance,
    max_distance_to_vertices,
    minimum_enclosing_circle,
)
from .models import Measurement, Point, SourceTrack
from .planner import Q3BaselinePlanner


@dataclass(frozen=True)
class V5PredictionConfig:
    """Fixed, reproducible geometry-prediction settings for V5."""

    sample_seed: int = 20260911
    sample_count: int = 12
    bearing_error_offsets_deg: tuple[float, ...] = (-1.0, 0.0, 1.0)
    candidate_radii_m: tuple[float, ...] = (500.0, 950.0)
    candidate_angle_step_deg: float = 30.0
    guaranteed_receive_distance_m: float = 995.0
    repeat_distance_m: float = 10.0
    robot_speed_mps: float = 5.0
    measure_time_s: float = 5.0
    clear_time_s: float = 5.0


@dataclass(frozen=True)
class CandidatePrediction:
    point: Point
    p_clear: float
    expected_mec_after_m: float
    expected_remaining_time_s: float
    expected_total_incremental_time_s: float
    outcome_count: int


def _triangle_area2(a: Point, b: Point, c: Point) -> float:
    return abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x))


def sample_feasible_polygon(poly: list[Point], count: int, seed: int) -> list[Point]:
    """Uniformly sample a convex feasible polygon with a fixed local RNG."""
    if not poly or count <= 0:
        return []
    if len(poly) < 3:
        return [poly[i % len(poly)] for i in range(count)]

    anchor = poly[0]
    triangles: list[tuple[Point, Point, Point]] = []
    cumulative: list[float] = []
    total = 0.0
    for i in range(1, len(poly) - 1):
        tri = (anchor, poly[i], poly[i + 1])
        area2 = _triangle_area2(*tri)
        if area2 <= 1e-12:
            continue
        total += area2
        triangles.append(tri)
        cumulative.append(total)
    if not triangles:
        return [poly[i % len(poly)] for i in range(count)]

    rng = random.Random(seed)
    samples: list[Point] = []
    for _ in range(count):
        tri_idx = min(bisect.bisect_left(cumulative, rng.random() * total), len(triangles) - 1)
        a, b, c = triangles[tri_idx]
        root = math.sqrt(rng.random())
        v = rng.random()
        wa = 1.0 - root
        wb = root * (1.0 - v)
        wc = root * v
        samples.append(Point(wa * a.x + wb * b.x + wc * c.x, wa * a.y + wb * b.y + wc * c.y))
    return samples


def candidate_grid(circle: Circle, config: V5PredictionConfig) -> list[Point]:
    points = [circle.center]
    steps = int(round(360.0 / config.candidate_angle_step_deg))
    for radius in config.candidate_radii_m:
        for i in range(steps):
            angle = math.radians(i * config.candidate_angle_step_deg)
            points.append(Point(circle.center.x + radius * math.cos(angle), circle.center.y + radius * math.sin(angle)))
    return points


def eligible_candidates(
    track: SourceTrack,
    region: list[Point],
    circle: Circle,
    config: V5PredictionConfig,
    extra_points: tuple[Point, ...] = (),
) -> list[Point]:
    points = candidate_grid(circle, config) + list(extra_points)
    eligible: list[Point] = []
    seen: set[tuple[int, int]] = set()
    for point in points:
        key = (round(point.x * 1_000_000), round(point.y * 1_000_000))
        if key in seen:
            continue
        seen.add(key)
        if max_distance_to_vertices(point, region) > config.guaranteed_receive_distance_m:
            continue
        if any(distance(point, m.position) < config.repeat_distance_m for m in track.direction_measurements):
            continue
        eligible.append(point)
    return eligible


def _fallback_point(
    measurements: list[Measurement],
    region: list[Point],
    circle: Circle,
    current: Point,
    config: V5PredictionConfig,
) -> Point:
    synthetic = SourceTrack(measurements[0].channel if measurements else 0)
    synthetic.measurements = list(measurements)
    best = circle.center
    best_score = -float("inf")
    for point in candidate_grid(circle, config):
        if max_distance_to_vertices(point, region) > config.guaranteed_receive_distance_m:
            continue
        quality = Q3BaselinePlanner.crossing_quality(synthetic, point, circle.center)
        move_penalty = distance(current, point) / 5000.0
        repeat_penalty = 1.0 if any(
            distance(point, m.position) < config.repeat_distance_m for m in synthetic.direction_measurements
        ) else 0.0
        score = quality - move_penalty - repeat_penalty
        if score > best_score:
            best_score = score
            best = point
    return best


def predict_candidate(
    track: SourceTrack,
    region: list[Point],
    candidate: Point,
    current_position: Point,
    samples: list[Point],
    config: V5PredictionConfig,
    mandatory_search_point: bool = False,
) -> CandidatePrediction:
    """Estimate one-step clearance and remaining completion time from visible geometry."""
    clearable = 0
    mec_values: list[float] = []
    remaining_times: list[float] = []
    outcome_count = 0

    for possible_source in samples:
        if distance(candidate, possible_source) <= 5.0:
            for _ in config.bearing_error_offsets_deg:
                clearable += 1
                outcome_count += 1
                mec_values.append(0.0)
                remaining_times.append(config.clear_time_s)
            continue

        true_bearing = math.degrees(
            math.atan2(possible_source.y - candidate.y, possible_source.x - candidate.x)
        ) % 360.0
        for error_deg in config.bearing_error_offsets_deg:
            reported = round((true_bearing + error_deg) % 360.0, 2)
            after_region = clip_bearing_wedge(region, candidate, reported)
            if not after_region:
                continue
            after_circle = minimum_enclosing_circle(after_region)
            outcome_count += 1
            mec_values.append(after_circle.radius)
            if after_circle.radius <= 20.0:
                clearable += 1
                remaining_times.append(
                    distance(candidate, after_circle.center) / config.robot_speed_mps + config.clear_time_s
                )
                continue

            synthetic_measure = Measurement(candidate, track.channel, "direction", reported, None)
            fallback = _fallback_point(
                track.direction_measurements + [synthetic_measure],
                after_region,
                after_circle,
                candidate,
                config,
            )
            remaining_times.append(
                distance(candidate, fallback) / config.robot_speed_mps
                + config.measure_time_s
                + distance(fallback, after_circle.center) / config.robot_speed_mps
                + config.clear_time_s
            )

    if outcome_count == 0:
        return CandidatePrediction(candidate, 0.0, float("inf"), float("inf"), float("inf"), 0)

    move_time = 0.0 if mandatory_search_point else distance(current_position, candidate) / config.robot_speed_mps
    expected_remaining = sum(remaining_times) / len(remaining_times)
    return CandidatePrediction(
        point=candidate,
        p_clear=clearable / outcome_count,
        expected_mec_after_m=sum(mec_values) / len(mec_values),
        expected_remaining_time_s=expected_remaining,
        expected_total_incremental_time_s=move_time + config.measure_time_s + expected_remaining,
        outcome_count=outcome_count,
    )

```

## q3/v6_policy.py

Role: final-runner dependency in RARC / frozen V6 / n=8.

```python
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .geometry import distance, max_distance_to_vertices
from .models import ChannelStatus, Point, SourceTrack
from .offline_policy import OfficialClientRunnerAdapter, Task
from .routing import optimize_open_route
from .v5_policy import DiagnosticDynamicRoutingPolicy
from .v5_prediction import (
    CandidatePrediction,
    V5PredictionConfig,
    eligible_candidates,
    predict_candidate,
    sample_feasible_polygon,
)


@dataclass(frozen=True)
class RouteAwareCandidate:
    point: Point
    search_index: int | None
    p_clear: float
    expected_mec_after_m: float
    route_marginal_s: float
    c_before_s: float
    c_with_s: float
    expected_future_cost_s: float
    objective_s: float


@dataclass(frozen=True)
class RouteAwareDecision:
    selected: RouteAwareCandidate
    highest_p_clear: RouteAwareCandidate

    @property
    def abandoned_high_p_clear(self) -> bool:
        return self.selected.p_clear + 1e-12 < self.highest_p_clear.p_clear


class RouteAwareSupplementPolicy(DiagnosticDynamicRoutingPolicy):
    """V6: route-aware FOUND-source MEASURE task generation on top of V4."""

    variant = "v6"

    def __init__(
        self,
        runner: Any,
        n: int = 8,
        prediction_config: V5PredictionConfig | None = None,
    ):
        super().__init__(runner, n=n)
        self.prediction_config = prediction_config or V5PredictionConfig()
        self._sample_cache: dict[tuple, list[Point]] = {}
        self._prediction_cache: dict[tuple, CandidatePrediction] = {}
        self._route_cache: dict[tuple, float] = {}
        self._selected_decisions: dict[int, RouteAwareDecision] = {}

    @staticmethod
    def _track_key(track: SourceTrack) -> tuple:
        return tuple((m.position.x, m.position.y, m.svd_deg) for m in track.direction_measurements)

    @staticmethod
    def _task_key(task: Task) -> tuple:
        return (
            task.kind,
            task.channel,
            round(task.point.x, 6),
            round(task.point.y, 6),
            task.search_index,
        )

    def route_travel_time(self, start: Point, tasks: list[Task]) -> float:
        key = (
            round(start.x, 6),
            round(start.y, 6),
            tuple(self._task_key(task) for task in tasks),
        )
        cached = self._route_cache.get(key)
        if cached is not None:
            return cached
        ordered = optimize_open_route(start, tasks)
        current = start
        route_m = 0.0
        for task in ordered:
            route_m += distance(current, task.point)
            current = task.point
        route_s = route_m / self.prediction_config.robot_speed_mps
        self._route_cache[key] = route_s
        return route_s

    def samples_for(self, track: SourceTrack, region: list[Point]) -> list[Point]:
        key = (track.channel, self._track_key(track))
        if key not in self._sample_cache:
            seed = (
                self.prediction_config.sample_seed
                + track.channel * 1009
                + len(track.direction_measurements) * 9176
            )
            self._sample_cache[key] = sample_feasible_polygon(
                region,
                self.prediction_config.sample_count,
                seed,
            )
        return self._sample_cache[key]

    def geometry_prediction(
        self,
        track: SourceTrack,
        region: list[Point],
        point: Point,
    ) -> CandidatePrediction:
        key = (
            track.channel,
            self._track_key(track),
            round(point.x, 6),
            round(point.y, 6),
        )
        prediction = self._prediction_cache.get(key)
        if prediction is None:
            prediction = predict_candidate(
                track,
                region,
                point,
                self.client.current_position,
                self.samples_for(track, region),
                self.prediction_config,
                mandatory_search_point=True,
            )
            self._prediction_cache[key] = prediction
        return prediction

    def search_index_for_point(self, point: Point) -> int | None:
        for idx in self.remaining_search_indices:
            if distance(point, self.search_points[idx]) <= 1e-6:
                return idx
        return None

    def candidate_points(
        self,
        track: SourceTrack,
        region: list[Point],
        v4_point: Point,
    ) -> list[Point]:
        circle = self.localization_circle(track)
        if circle is None:
            return [v4_point]
        search_points = tuple(
            self.search_points[idx]
            for idx in sorted(self.remaining_search_indices)
            if max_distance_to_vertices(self.search_points[idx], region)
            <= self.prediction_config.guaranteed_receive_distance_m
            and not any(
                distance(self.search_points[idx], measurement.position)
                < self.prediction_config.repeat_distance_m
                for measurement in track.direction_measurements
            )
        )
        points = eligible_candidates(
            track,
            region,
            circle,
            self.prediction_config,
            extra_points=(v4_point, *search_points),
        )
        if not any(distance(v4_point, point) <= 1e-6 for point in points):
            points.append(v4_point)
        return points

    def route_aware_candidate(
        self,
        track: SourceTrack,
        region: list[Point],
        point: Point,
        context_tasks: list[Task],
    ) -> RouteAwareCandidate:
        prediction = self.geometry_prediction(track, region, point)
        c_before = self.route_travel_time(self.client.current_position, context_tasks)
        candidate_task = Task("measure", track.channel, point)
        c_with = self.route_travel_time(
            self.client.current_position,
            context_tasks + [candidate_task],
        )
        # Exact open-route cost is monotone under task insertion. The clamp only
        # removes negative artifacts caused by the frozen heuristic router.
        route_marginal = max(0.0, c_with - c_before)
        objective = (
            route_marginal
            + self.prediction_config.measure_time_s
            + prediction.expected_remaining_time_s
        )
        return RouteAwareCandidate(
            point=point,
            search_index=self.search_index_for_point(point),
            p_clear=prediction.p_clear,
            expected_mec_after_m=prediction.expected_mec_after_m,
            route_marginal_s=route_marginal,
            c_before_s=c_before,
            c_with_s=c_with,
            expected_future_cost_s=prediction.expected_remaining_time_s,
            objective_s=objective,
        )

    def route_aware_decision(
        self,
        track: SourceTrack,
        region: list[Point],
        v4_point: Point,
        context_tasks: list[Task],
    ) -> RouteAwareDecision:
        estimates = [
            self.route_aware_candidate(track, region, point, context_tasks)
            for point in self.candidate_points(track, region, v4_point)
        ]
        selected = min(estimates, key=lambda item: (item.objective_s, -item.p_clear))
        highest = max(estimates, key=lambda item: (item.p_clear, -item.objective_s))
        return RouteAwareDecision(selected, highest)

    def build_dynamic_tasks(self) -> list[Task]:
        self._wait_assignments = {}
        self._selected_decisions = {}
        search_tasks: list[Task] = []
        if self.discovered_count() < 16:
            for idx in sorted(self.remaining_search_indices):
                point = self.search_points[idx]
                if self.channels_to_scan_search_point(idx):
                    search_tasks.append(Task("search", 0, point, search_index=idx))

        clear_tasks = self.ready_clear_tasks()
        clear_channels = {task.channel for task in clear_tasks}
        v4_measure_tasks: dict[int, Task] = {}
        for track in self.tracks.values():
            if track.status != ChannelStatus.FOUND or track.channel in clear_channels:
                continue
            point = self.localization_candidate(track)
            if point is not None:
                v4_measure_tasks[track.channel] = Task("measure", track.channel, point)

        provisional = search_tasks + clear_tasks + list(v4_measure_tasks.values())
        selected_tasks = search_tasks + clear_tasks
        for channel, v4_task in v4_measure_tasks.items():
            track = self.tracks[channel]
            region, circle = self.localization_state(track)
            if not region or circle is None:
                selected_tasks.append(v4_task)
                continue
            context = [
                task
                for task in provisional
                if not (task.kind == "measure" and task.channel == channel)
            ]
            decision = self.route_aware_decision(track, region, v4_task.point, context)
            self._selected_decisions[channel] = decision
            if decision.selected.search_index is not None:
                self._wait_assignments[channel] = decision.selected.search_index
            else:
                selected_tasks.append(Task("measure", channel, decision.selected.point))
        return selected_tasks

    def channels_to_scan_search_point(self, search_index: int) -> list[int]:
        channels = set(super().channels_to_scan_search_point(search_index))
        channels.update(
            channel
            for channel, assigned_index in self._wait_assignments.items()
            if assigned_index == search_index and self.tracks[channel].status == ChannelStatus.FOUND
        )
        ordered = sorted(channels)
        if search_index % 2 == 1:
            ordered.reverse()
        return ordered

    def measure_channel(self, point: Point, channel: int) -> None:
        status_before = self.tracks[channel].status
        decision = self._selected_decisions.get(channel)
        super().measure_channel(point, channel)
        if (
            status_before != ChannelStatus.FOUND
            or decision is None
            or distance(point, decision.selected.point) > 1e-6
        ):
            return
        selected = decision.selected
        highest = decision.highest_p_clear
        self.emit(
            "route_supplement_execution",
            channel=channel,
            time_s=self.client.last_virtual_time_s,
            selected_x=selected.point.x,
            selected_y=selected.point.y,
            selected_search_index=selected.search_index,
            selected_p_clear=selected.p_clear,
            selected_route_marginal_s=selected.route_marginal_s,
            selected_expected_future_cost_s=selected.expected_future_cost_s,
            selected_objective_s=selected.objective_s,
            highest_p_clear_x=highest.point.x,
            highest_p_clear_y=highest.point.y,
            highest_p_clear=highest.p_clear,
            highest_p_clear_route_marginal_s=highest.route_marginal_s,
            highest_p_clear_objective_s=highest.objective_s,
            abandoned_high_p_clear=decision.abandoned_high_p_clear,
        )


def policy_v6(runner: Any, n: int = 8) -> None:
    RouteAwareSupplementPolicy(runner, n=n).run()


def policy_v6_official(client: Any, n: int = 8) -> RouteAwareSupplementPolicy:
    """Run V6 against the official HTTP client after external practice gating."""
    policy = RouteAwareSupplementPolicy(OfficialClientRunnerAdapter(client), n=n)
    policy.run()
    return policy

```

