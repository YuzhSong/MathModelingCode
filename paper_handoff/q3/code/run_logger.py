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
