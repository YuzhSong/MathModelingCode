"""Static, reproducible audit for the W5Pro V3 engineering checklist.

This is intentionally a lightweight gate: it verifies the architectural
invariants that can be checked without running a mission.  Runtime behavior
is covered by the ``test_w5pro*.py`` suite and benchmark artifacts.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditItem:
    key: str
    ok: bool
    detail: str


REQUIRED_MODULES = {
    "config": "w5pro_config.py",
    "policy": "w5pro_policy.py",
    "hypothesis": "w5pro_hypothesis.py",
    "certificate": "w5pro_triangle_certificate.py",
    "tasks": "w5pro_tasks.py",
    "planner": "w5pro_planner.py",
    "safety": "w5pro_safety.py",
    "scheduler": "w5pro_scheduler.py",
    "metrics": "w5pro_metrics.py",
}
FORBIDDEN_MODULES = {"torch", "tensorflow", "stable_baselines", "stable_baselines3"}


def audit(root: Path | str | None = None) -> list[AuditItem]:
    root = Path(root or Path(__file__).resolve().parents[1])
    q4 = root / "q4"
    items: list[AuditItem] = []
    for key, filename in REQUIRED_MODULES.items():
        path = q4 / filename
        items.append(AuditItem(f"module.{key}", path.is_file(), str(path)))

    config_text = (q4 / REQUIRED_MODULES["config"]).read_text(encoding="utf-8")
    items.append(AuditItem("identity.mode", "IDENTITY_CONFIG" in config_text and "identity" in config_text,
                           "W5ProConfig exposes identity configuration"))
    policy_text = (q4 / REQUIRED_MODULES["policy"]).read_text(encoding="utf-8")
    items.append(AuditItem("hard.fallback", "W5SymmetricDetectionPolicy" in policy_text,
                           "policy subclasses the frozen W5 skeleton"))
    cert_text = (q4 / REQUIRED_MODULES["certificate"]).read_text(encoding="utf-8")
    items.append(AuditItem("hard.certificate", "verify_continuous_mesh" in cert_text and "point_in_triangle" in cert_text,
                           "triangle certificate and mesh audit are present"))

    violations = []
    for path in q4.glob("w5pro_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name in FORBIDDEN_MODULES:
                    violations.append(f"{path.name}:{name}")
    items.append(AuditItem("no.ml.runtime", not violations,
                           "; ".join(violations) or "no forbidden ML runtime tokens"))

    # Ensure all W5Pro modules remain syntactically parseable.
    parse_errors = []
    for path in q4.glob("w5pro_*.py"):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            parse_errors.append(f"{path.name}:{exc.lineno}")
    items.append(AuditItem("syntax", not parse_errors, "; ".join(parse_errors) or "all modules parse"))
    return items


if __name__ == "__main__":
    results = audit()
    for item in results:
        print(f"[{ 'PASS' if item.ok else 'FAIL' }] {item.key}: {item.detail}")
    raise SystemExit(0 if all(item.ok for item in results) else 1)
