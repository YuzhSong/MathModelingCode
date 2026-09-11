"""
蒙特卡洛试验场：把一个"机器狗策略"跑在大量随机/极端案例上，直接调用 engine
（不走 HTTP，快）并统一汇总指标。

指标（对齐题目最重要的约束"确保所有干扰源被清除"）：
  - success_rate         全清成功率 P(clear all)   ← 首要
  - time mean/P50/P90/P95/max（虚拟秒）             ← 其次
  - movement 距离、频道切换次数、measure 次数、clear 次数、clear 失败次数、near 次数
成功率优先：一个平均更快但偶尔漏源的策略，未必优于稍慢但 100% 清除的策略。

策略接口（鸭子类型）：可调用对象 policy(runner) -> None，用 runner 提供的
enter/measure/clear/exit 与状态查询完成一局。它对真值不可见，只能看接口返回。
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field as dc_field
from typing import Callable, Optional

from .case import Case, generate_case, generate_stress_case
from .engine import Engine


@dataclass
class ActionRecord:
    """Policy-visible action endpoint recorded for post-episode oracle analysis."""
    action: str
    x: float
    y: float
    channel: int
    result: str


@dataclass
class EpisodeResult:
    """单局结果。"""
    cleared: int = 0
    total: int = 0
    success: bool = False              # 是否全部清除
    virtual_time_s: float = 0.0
    move_distance_m: float = 0.0
    move_time_s: float = 0.0
    channel_switch_time_s: float = 0.0
    measure_action_time_s: float = 0.0
    clear_action_time_s: float = 0.0
    n_measure: int = 0
    n_channel_switch: int = 0
    n_clear: int = 0
    n_clear_fail: int = 0              # clear 返回 no_target_in_range 的次数
    n_near: int = 0
    action_log: list[ActionRecord] = dc_field(default_factory=list, repr=False)
    conditional_route_oracle_time_s: float | None = None
    conditional_route_oracle_method: str | None = None
    conditional_route_oracle_exact: bool = False
    conditional_route_oracle_gap: float | None = None
    full_oracle_proxy_time_s: float | None = None
    full_oracle_proxy_method: str | None = None
    full_oracle_proxy_exact_route: bool = False
    full_oracle_proxy_gap: float | None = None
    finished_reason: Optional[str] = None
    error: Optional[str] = None        # 策略抛异常时记录


class EpisodeRunner:
    """
    给策略用的一局运行器：封装 engine，记录动作统计。策略只能通过这里的方法与世界交互，
    看不到真值。所有动作在时限到达后返回 None，策略应据此结束。
    """

    def __init__(self, case: Case, engine: Optional[Engine] = None):
        self.case = case
        self.engine = engine or Engine(case)
        self.res = EpisodeResult(total=case.total)
        self._entered = False
        self._last_x = 0.0
        self._last_y = 0.0

    # ---- 供策略调用的动作 ----
    def enter(self) -> Optional[dict]:
        d = self.engine.enter()
        self._entered = True
        return d

    def measure(self, x: float, y: float, channel: int) -> Optional[dict]:
        """返回 measure 响应 dict（含 measure_result / 可能的 svd_deg）；时限到→None。"""
        old_channel = self.engine.st.channel
        move_distance = math.hypot(x - self._last_x, y - self._last_y)
        resp, outcome = self.engine.measure(x, y, channel)
        if resp.get("__finished__"):
            self.res.finished_reason = self.engine.st.finish_reason
            return None
        self.res.move_distance_m += move_distance
        self.res.move_time_s += move_distance / 5.0
        if channel != old_channel:
            self.res.n_channel_switch += 1
            self.res.channel_switch_time_s += 1.0
        self.res.measure_action_time_s += 5.0
        self._last_x, self._last_y = x, y
        self.res.n_measure += 1
        if outcome is not None and outcome.result == "near":
            self.res.n_near += 1
        self.res.action_log.append(ActionRecord("measure", float(x), float(y), int(channel), outcome.result if outcome is not None else "finished"))
        return resp

    def clear(self, x: float, y: float, channel: int) -> Optional[dict]:
        move_distance = math.hypot(x - self._last_x, y - self._last_y)
        resp, outcome = self.engine.clear(x, y, channel)
        if resp.get("__finished__"):
            self.res.finished_reason = self.engine.st.finish_reason
            return None
        self.res.move_distance_m += move_distance
        self.res.move_time_s += move_distance / 5.0
        self._last_x, self._last_y = x, y
        self.res.n_clear += 1
        if outcome is not None and outcome.result != "success":
            self.res.n_clear_fail += 1
            self.res.clear_action_time_s += 3.0
        else:
            self.res.clear_action_time_s += 5.0
        self.res.action_log.append(ActionRecord("clear", float(x), float(y), int(channel), outcome.result if outcome is not None else "finished"))
        return resp

    def exit(self) -> Optional[dict]:
        return self.engine.exit()

    # ---- 状态查询（不泄露真值）----
    @property
    def virtual_time_s(self) -> float:
        return self.engine.st.virtual_time_s

    @property
    def position(self) -> tuple[float, float]:
        return (self.engine.st.pos_x, self.engine.st.pos_y)

    @property
    def current_channel(self) -> int:
        return self.engine.st.channel

    def finalize(self) -> EpisodeResult:
        self.res.cleared = self.case.cleared_count
        self.res.success = (self.res.cleared == self.res.total)
        self.res.virtual_time_s = self.engine.st.virtual_time_s
        if self.res.finished_reason is None:
            self.res.finished_reason = self.engine.st.finish_reason
        return self.res


class PolicyRunnerProxy:
    """
    Policy-facing runner surface. It intentionally exposes only the API-visible
    interaction methods and public state mirrors, not Case or engine internals.
    """

    __slots__ = ("_runner",)

    def __init__(self, runner: EpisodeRunner):
        self._runner = runner

    def enter(self) -> Optional[dict]:
        return self._runner.enter()

    def measure(self, x: float, y: float, channel: int) -> Optional[dict]:
        return self._runner.measure(x, y, channel)

    def clear(self, x: float, y: float, channel: int) -> Optional[dict]:
        return self._runner.clear(x, y, channel)

    def exit(self) -> Optional[dict]:
        return self._runner.exit()

    @property
    def virtual_time_s(self) -> float:
        return self._runner.virtual_time_s

    @property
    def position(self) -> tuple[float, float]:
        return self._runner.position

    @property
    def current_channel(self) -> int:
        return self._runner.current_channel


def run_episode(case: Case, policy: Callable[[EpisodeRunner], None]) -> EpisodeResult:
    """跑单局：交给 policy 驱动，返回统计。策略异常不致命，记录到 result.error。"""
    runner = EpisodeRunner(case)
    try:
        policy(PolicyRunnerProxy(runner))
    except Exception as e:  # 策略 bug 不应崩掉整个蒙特卡洛
        runner.res.error = f"{type(e).__name__}: {e}"
    result = runner.finalize()
    try:
        from q3.oracles import attach_oracle_benchmarks

        attach_oracle_benchmarks(case, result)
    except Exception as e:
        suffix = f"oracle_error={type(e).__name__}: {e}"
        result.error = suffix if not result.error else f"{result.error}; {suffix}"
    return result


@dataclass
class Metrics:
    """一批案例的汇总指标。"""
    n_episodes: int = 0
    n_success: int = 0
    n_error: int = 0
    success_rate: float = 0.0
    time_mean: float = 0.0
    time_p50: float = 0.0
    time_p90: float = 0.0
    time_p95: float = 0.0
    time_max: float = 0.0
    move_mean: float = 0.0
    move_time_mean: float = 0.0
    switch_mean: float = 0.0
    switch_time_mean: float = 0.0
    measure_mean: float = 0.0
    measure_time_mean: float = 0.0
    clear_mean: float = 0.0
    clear_success_mean: float = 0.0
    clear_time_mean: float = 0.0
    clear_fail_mean: float = 0.0
    near_mean: float = 0.0
    avg_time_per_source_mean: float = 0.0
    pooled_avg_time_per_source: float = 0.0
    time_component_delta_mean: float = 0.0
    time_component_delta_abs_max: float = 0.0
    conditional_route_oracle_time_mean: float = 0.0
    conditional_route_oracle_gap_mean: float = 0.0
    full_oracle_proxy_time_mean: float = 0.0
    full_oracle_proxy_gap_mean: float = 0.0
    # 仅在成功局上再算一份时间分布（避免失败局污染时间统计）
    time_mean_success: float = 0.0
    time_p95_success: float = 0.0
    time_max_success: float = 0.0
    results: list = dc_field(default_factory=list, repr=False)

    def report(self) -> str:
        lines = [
            f"episodes           : {self.n_episodes}",
            f"success_rate       : {self.success_rate*100:.2f}%  ({self.n_success}/{self.n_episodes})",
            f"errors             : {self.n_error}",
            f"time  mean/P50/P90/P95/max : "
            f"{self.time_mean:.1f} / {self.time_p50:.1f} / {self.time_p90:.1f} / "
            f"{self.time_p95:.1f} / {self.time_max:.1f}  s",
            f"time(success only) mean/P95/max : "
            f"{self.time_mean_success:.1f} / {self.time_p95_success:.1f} / "
            f"{self.time_max_success:.1f}  s",
            f"move  mean         : {self.move_mean:.1f} m",
            f"move time mean     : {self.move_time_mean:.1f} s",
            f"channel switch mean: {self.switch_mean:.2f}  ({self.switch_time_mean:.1f} s)",
            f"measure mean       : {self.measure_mean:.2f}",
            f"measure time mean  : {self.measure_time_mean:.1f} s",
            f"clear mean         : {self.clear_mean:.2f}  (fail mean {self.clear_fail_mean:.2f})",
            f"clear success mean : {self.clear_success_mean:.2f}",
            f"clear action mean  : {self.clear_time_mean:.1f} s",
            f"near mean          : {self.near_mean:.2f}",
            f"avg time/source    : {self.avg_time_per_source_mean:.1f} s",
            f"pooled avg/source  : {self.pooled_avg_time_per_source:.1f} s",
            f"time component delta mean/maxabs : {self.time_component_delta_mean:.6f} / {self.time_component_delta_abs_max:.6f} s",
            f"conditional oracle mean/gap : {self.conditional_route_oracle_time_mean:.1f} s / {self.conditional_route_oracle_gap_mean:.3f}",
            f"full-info proxy mean/gap    : {self.full_oracle_proxy_time_mean:.1f} s / {self.full_oracle_proxy_gap_mean:.3f}",
        ]
        return "\n".join(lines)


def _pct(sorted_vals: list[float], q: float) -> float:
    """线性插值分位数（q∈[0,1]）；空列表返回 0。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def aggregate(results: list[EpisodeResult]) -> Metrics:
    """把若干单局结果汇总为 Metrics。"""
    m = Metrics(results=results)
    m.n_episodes = len(results)
    if m.n_episodes == 0:
        return m
    m.n_success = sum(1 for r in results if r.success)
    m.n_error = sum(1 for r in results if r.error)
    m.success_rate = m.n_success / m.n_episodes

    times = sorted(r.virtual_time_s for r in results)
    m.time_mean = statistics.fmean(times)
    m.time_p50 = _pct(times, 0.50)
    m.time_p90 = _pct(times, 0.90)
    m.time_p95 = _pct(times, 0.95)
    m.time_max = times[-1]

    m.move_mean = statistics.fmean(r.move_distance_m for r in results)
    m.move_time_mean = statistics.fmean(r.move_time_s for r in results)
    m.switch_mean = statistics.fmean(r.n_channel_switch for r in results)
    m.switch_time_mean = statistics.fmean(r.channel_switch_time_s for r in results)
    m.measure_mean = statistics.fmean(r.n_measure for r in results)
    m.measure_time_mean = statistics.fmean(r.measure_action_time_s for r in results)
    m.clear_mean = statistics.fmean(r.n_clear for r in results)
    m.clear_success_mean = statistics.fmean(r.n_clear - r.n_clear_fail for r in results)
    m.clear_time_mean = statistics.fmean(r.clear_action_time_s for r in results)
    m.clear_fail_mean = statistics.fmean(r.n_clear_fail for r in results)
    m.near_mean = statistics.fmean(r.n_near for r in results)
    m.avg_time_per_source_mean = statistics.fmean(
        (r.virtual_time_s / r.cleared) if r.cleared else 0.0 for r in results
    )
    total_cleared = sum(r.cleared for r in results)
    m.pooled_avg_time_per_source = sum(r.virtual_time_s for r in results) / total_cleared if total_cleared else 0.0
    component_deltas = [
        r.virtual_time_s - (r.move_time_s + r.measure_action_time_s + r.channel_switch_time_s + r.clear_action_time_s)
        for r in results
    ]
    m.time_component_delta_mean = statistics.fmean(component_deltas)
    m.time_component_delta_abs_max = max(abs(v) for v in component_deltas)
    conditional_times = [r.conditional_route_oracle_time_s for r in results if r.conditional_route_oracle_time_s is not None]
    conditional_gaps = [r.conditional_route_oracle_gap for r in results if r.conditional_route_oracle_gap is not None]
    full_times = [r.full_oracle_proxy_time_s for r in results if r.full_oracle_proxy_time_s is not None]
    full_gaps = [r.full_oracle_proxy_gap for r in results if r.full_oracle_proxy_gap is not None]
    if conditional_times:
        m.conditional_route_oracle_time_mean = statistics.fmean(conditional_times)
    if conditional_gaps:
        m.conditional_route_oracle_gap_mean = statistics.fmean(conditional_gaps)
    if full_times:
        m.full_oracle_proxy_time_mean = statistics.fmean(full_times)
    if full_gaps:
        m.full_oracle_proxy_gap_mean = statistics.fmean(full_gaps)

    succ_times = sorted(r.virtual_time_s for r in results if r.success)
    if succ_times:
        m.time_mean_success = statistics.fmean(succ_times)
        m.time_p95_success = _pct(succ_times, 0.95)
        m.time_max_success = succ_times[-1]
    return m


def evaluate(
    policy: Callable[[EpisodeRunner], None],
    n_cases: int = 200,
    problem: int = 3,
    base_seed: int = 0,
    field_kind: str = "smooth",
    field_params: Optional[dict] = None,
) -> Metrics:
    """在 n_cases 个随机案例上评估策略，返回汇总指标。每个案例 seed = base_seed+i 可复现。"""
    results = []
    for i in range(n_cases):
        case = generate_case(seed=base_seed + i, problem=problem,
                             field_kind=field_kind, field_params=field_params,
                             mode="formal")
        results.append(run_episode(case, policy))
    return aggregate(results)


def evaluate_stress(
    policy: Callable[[EpisodeRunner], None],
    stress_type: str,
    n_cases: int = 50,
    problem: int = 3,
    base_seed: int = 0,
    field_kind: str = "adversarial",
    field_params: Optional[dict] = None,
    scan_points: Optional[list[tuple[float, float]]] = None,
) -> Metrics:
    """在某一类极端案例上评估策略。"""
    results = []
    for i in range(n_cases):
        case = generate_stress_case(stress_type, seed=base_seed + i, problem=problem,
                                    field_kind=field_kind, field_params=field_params,
                                    scan_points=scan_points, mode="formal")
        results.append(run_episode(case, policy))
    return aggregate(results)
