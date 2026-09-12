from __future__ import annotations

import contextlib
import importlib
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WAY1_ROOT = ROOT / "external" / "SXJM-way1" / "Way1" / "radio_locator"
WAY3_ROOT = ROOT / "external" / "SXJM-way3" / "Way3"


@contextlib.contextmanager
def prepend_path(path: Path):
    text = str(path)
    inserted = False
    if text not in sys.path:
        sys.path.insert(0, text)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(text)


class Way1RunnerSim:
    """Adapter from our offline runner API to Way1's simulator response shape."""

    def __init__(self, runner: Any):
        self.runner = runner

    def enter(self):
        with prepend_path(WAY1_ROOT):
            protocol = importlib.import_module("src.simulator.protocol")
        resp = self.runner.enter()
        return protocol.EnterResponse(
            accepted=resp is not None,
            virtual_time_s=0.0 if resp is None else float(resp.get("virtual_time_s", 0.0)),
            max_virtual_duration_s=360000.0,
            max_real_duration_s=1200.0,
            remaining_real_duration_s=1200,
        )

    def measure(self, x: float, y: float, channel: int):
        with prepend_path(WAY1_ROOT):
            protocol = importlib.import_module("src.simulator.protocol")
        resp = self.runner.measure(float(x), float(y), int(channel))
        if resp is None:
            return protocol.MeasureResponse(accepted=False)
        return protocol.MeasureResponse(
            accepted=True,
            virtual_time_s=float(resp.get("virtual_time_s", 0.0)),
            measure_result=resp.get("measure_result"),
            svd_deg=resp.get("svd_deg"),
        )

    def clear(self, x: float, y: float, channel: int):
        with prepend_path(WAY1_ROOT):
            protocol = importlib.import_module("src.simulator.protocol")
        resp = self.runner.clear(float(x), float(y), int(channel))
        if resp is None:
            return protocol.ClearResponse(accepted=False)
        return protocol.ClearResponse(
            accepted=True,
            virtual_time_s=float(resp.get("virtual_time_s", 0.0)),
            clear_result=resp.get("clear_result"),
        )

    def exit(self):
        with prepend_path(WAY1_ROOT):
            protocol = importlib.import_module("src.simulator.protocol")
        resp = self.runner.exit()
        return protocol.ExitResponse(
            accepted=resp is not None,
            virtual_time_s=0.0 if resp is None else float(resp.get("virtual_time_s", 0.0)),
            exit_reason=None,
        )


def policy_way1(runner: Any) -> None:
    """Run Way1 Q3 controller on our unified offline_sim runner."""
    with prepend_path(WAY1_ROOT):
        q3_hex_cover = importlib.import_module("src.coverage.q3_hex_cover")
        types = importlib.import_module("src.domain.types")
        world_state = importlib.import_module("src.domain.world_state")
        controller_mod = importlib.import_module("src.runtime.controller")

    problem = types.ProblemConstants()
    robot = types.RobotConstants()
    world = world_state.WorldState(problem=problem, robot=robot)
    plan = q3_hex_cover.hex_cover(
        problem.area_radius,
        r_safe=980.0,
        m=6,
    )
    ctrl = controller_mod.Controller(
        Way1RunnerSim(runner),
        world,
        plan.points,
        controller_mod.ControllerConfig(
            problem_mode="q3",
            coarse_size=40.0,
            fine_size=15.0,
            max_steps=3000,
            lam=1.0,
            max_candidates=48,
        ),
    )
    ctrl.run()
    recorder = getattr(runner, "record_policy_diagnostic", None)
    if recorder is not None:
        recorder(
            {
                "event": "way1_summary",
                "steps": world.step,
                "cleared": world.cleared_count(),
                "absent": world.confirmed_absent(),
                "mission_complete": world.mission_complete(),
                "cover_points": len(plan.points),
                "covers_arena": bool(plan.covers_arena),
                "safe_radius_m": float(plan.safe_radius),
            }
        )
        for item in ctrl.log:
            recorder(
                {
                    "event": "way1_step",
                    "step": item.step,
                    "kind": item.kind,
                    "channel": item.channel,
                    "x": None if item.location is None else float(item.location[0]),
                    "y": None if item.location is None else float(item.location[1]),
                    "time_s": float(item.virtual_time),
                    "mec_radius_m": item.mec_radius,
                    "note": item.note,
                }
            )


def policy_way3(runner: Any) -> None:
    """Run Way3 Hunter Q3 policy through its RunnerWorld adapter."""
    with prepend_path(WAY3_ROOT):
        agent = importlib.import_module("jammerhunt.agent")
        interface = importlib.import_module("jammerhunt.interface")

    hunter = agent.Hunter(problem=3)
    hunter.run(interface.RunnerWorld(runner))
    recorder = getattr(runner, "record_policy_diagnostic", None)
    if recorder is not None:
        recorder(
            {
                "event": "way3_summary",
                "cleared": hunter.cleared_count,
                "scan_points": len(hunter.scan_points()),
                "clear_margin_m": hunter.clear_margin_m,
                "prune_radius_m": hunter.prune_radius_m,
                "orbit_radius_m": hunter.orbit_radius_m,
                "orbit_delta_deg": hunter.orbit_delta_deg,
                "max_homing_iters": hunter.max_homing_iters,
            }
        )
