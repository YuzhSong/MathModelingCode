"""Generate a conservative, evidence-linked W5Pro checklist inventory."""
from __future__ import annotations

import csv
import re
from pathlib import Path


ITEM = re.compile(r"^\s*\* \[ \] \*\*(P[012]-[A-Z0-9-]+|P[012]-\d+)[^｜|]*[｜|](.*)$")
MODULE = re.compile(r"q4/([A-Za-z0-9_]+\.py)")
ID_MODULES = {
    "P0-T08": "w5pro_triangle_certificate.py", "P0-T11": "w5pro_policy.py",
    "P0-B02": "w5pro_feasible.py", "P0-S02": "w5pro_scheduler.py",
    "P0-S04": "w5pro_hypothesis.py", "P1-G01": "w5pro_rotation.py",
    "P1-G03": "w5pro_rotation.py", "P1-G04": "w5pro_rotation.py",
    "P0-Q02": "w5pro_scheduler.py", "P0-Q04": "w5pro_tasks.py",
    "P1-I01": "w5pro_information_ridge.py", "P1-I02": "w5pro_information_ridge.py",
    "P1-I03": "w5pro_information_ridge.py", "P1-I04": "w5pro_information_ridge.py",
    "P0-E01": "w5pro_hypothesis.py", "P1-R03": "w5pro_corridor.py",
    "P2-R10": "w5pro_tspn.py", "P1-O01": "w5pro_outcomes.py",
    "P1-O03": "w5pro_future_cost.py", "P1-G12": "w5pro_geometry_sweep.py",
}
CONTRACT_TEST_IDS = {
    "P0-001", "P0-002", "P0-003", "P0-007", "P0-008", "P0-033",
    "P0-034", "P0-005", "P0-006", "P0-140", "P0-240", "P0-L01", "P0-L02", "P0-L03",
}
EXPLICIT_TESTS = {
    **{f"P0-{i:03d}": "test_w5pro_backbone.py" for i in (40, 41, 42, 44, 45, 46, 47, 48)},
    "P0-052": "test_w5pro_backbone.py", "P0-053": "test_w5pro_backbone.py",
    "P0-054": "test_w5pro_backbone.py",
    "P0-Q01": "test_w5pro_scheduler.py", "P0-Q02": "test_w5pro_scheduler.py",
    "P0-Q03": "test_w5pro_scheduler.py", "P0-Q04": "test_w5pro_state_tasks.py",
    "P0-Q05": "test_w5pro_scheduler.py",
    "P0-E03": "test_w5pro_nbv.py", "P0-E04": "test_w5pro_nbv.py",
    "P0-E05": "test_w5pro_nbv.py", "P0-080": "test_w5pro_nbv.py",
    "P0-081": "test_w5pro_nbv.py", "P0-082": "test_w5pro_nbv.py",
    "P0-083": "test_w5pro_nbv.py", "P0-084": "test_w5pro_nbv.py",
    "P0-085": "test_w5pro_nbv.py", "P0-087": "test_w5pro_nbv.py",
    "P0-088": "test_w5pro_nbv.py",
    "P0-L04": "test_w5pro_safety.py",
    "P0-T01": "test_w5pro_triangle_certificate.py", "P0-T02": "test_w5pro_triangle_certificate.py",
    "P0-T03": "test_w5pro_triangle_certificate.py", "P0-T04": "test_w5pro_triangle_certificate.py",
    "P0-T05": "test_w5pro_triangle_certificate.py", "P0-T06": "test_w5pro_triangle_certificate.py",
    "P0-T07": "test_w5pro_triangle_certificate.py", "P0-T08": "test_w5pro_triangle_certificate.py",
    **{f"P0-S0{i}": "test_w5pro_scheduler.py" for i in range(1, 6)},
    "P1-I01": "test_w5pro_information.py", "P1-I02": "test_w5pro_information.py",
    "P1-I03": "test_w5pro_information.py", "P1-I04": "test_w5pro_information.py",
    "P1-R01": "test_w5pro_corridor.py", "P1-R02": "test_w5pro_corridor.py",
    "P1-R03": "test_w5pro_corridor.py",
    "P0-140": "test_w5pro_planner.py", "P0-141": "test_w5pro_planner.py",
    "P0-143": "test_w5pro_planner.py", "P0-144": "test_w5pro_planner.py",
    "P0-145": "test_w5pro_planner.py", "P0-150": "test_w5pro_planner.py",
    "P0-151": "test_w5pro_planner.py", "P0-152": "test_w5pro_planner.py",
    "P0-153": "test_w5pro_planner.py", "P0-154": "test_w5pro_planner.py",
    "P0-155": "test_w5pro_planner.py",
    "P0-160": "test_w5pro_clear_route.py", "P0-161": "test_w5pro_clear_route.py",
    "P0-162": "test_w5pro_clear_route.py", "P0-164": "test_w5pro_clear_route.py",
    "P0-165": "test_w5pro_clear_route.py", "P0-166": "test_w5pro_clear_route.py",
    **{f"P0-{i:03d}": "test_w5pro_state_tasks.py" for i in (90, 92, 93, 94, 97, 105, 106, 107, 108, 109, 112, 120, 121, 122, 125, 127, 129, 130)},
    "P0-004": "test_w5pro_foundation.py",
    **{f"P0-{i:03d}": "test_w5pro_hypothesis.py" for i in (20, 21, 22, 23, 27, 28)},
    "P0-011": "test_w5pro_state_tasks.py", "P0-012": "test_w5pro_state_tasks.py",
    "P0-014": "test_w5pro_checklist_contract.py", "P0-015": "test_w5pro_checklist_contract.py",
    "P0-086": "test_w5pro_diagnostics.py", "P0-095": "test_w5pro_state_tasks.py",
    **{f"P0-{i:03d}": "test_w5pro_corridor.py" for i in (100, 101, 102, 103, 104)},
    "P0-T10": "test_w5pro_triangle_certificate.py", "P0-T11": "test_w5pro_triangle_certificate.py",
    "P0-T13": "test_w5pro_triangle_certificate.py",
    "P0-B05": "test_w5pro_feasible.py",
    "P0-024": "test_w5pro_hypothesis.py", "P0-031": "test_w5pro_hypothesis.py",
    "P0-035": "test_w5pro_hypothesis.py", "P0-032": "test_w5pro_checklist_contract.py",
    "P0-043": "test_w5pro_backbone.py", "P0-049": "test_w5pro_backbone.py",
    **{f"P0-{i:03d}": "test_w5pro_nbv.py" for i in (60, 63, 64, 65, 66, 67, 68, 69, 70, 71)},
    "P0-062": "test_w5pro_tail_fallback.py",
    **{f"P1-{i:03d}": "test_w5pro_scheduler.py" for i in (170, 171, 172, 173, 175, 177, 178, 179, 180, 182, 183)},
    **{f"P1-{i:03d}": "test_w5pro_clear_route.py" for i in (190, 191, 193, 194, 195, 200, 201, 204, 205)},
    **{f"P1-{i:03d}": "test_w5pro_clear_route.py" for i in (210, 211, 212, 213, 215)},
    **{f"P1-{i:03d}": "test_w5pro_nbv.py" for i in (220, 221, 222, 223, 224)},
    **{f"P2-{i:03d}": "test_w5pro_tail_fallback.py" for i in (230, 231, 232, 236)},
    "P0-123": "test_w5pro_clear_route.py", "P0-124": "test_w5pro_clear_route.py",
    "P0-128": "test_w5pro_clear_route.py",
    **{f"P0-{i:03d}": "test_w5pro_planner.py" for i in (142, 146, 147, 148)},
    "P0-241": "test_w5pro_planner.py",
    **{f"P1-G0{i}": "test_w5pro_rotation.py" for i in range(1, 6)},
    "P1-Q11": "test_w5pro_scheduler.py",
    "P0-E01": "test_w5pro_feasible.py", "P0-E02": "test_w5pro_feasible.py",
    "P1-R04": "test_w5pro_corridor.py",
    "P2-R10": "test_w5pro_tspn.py", "P2-R12": "test_w5pro_tspn.py",
    **{f"P1-P0{i}": "test_w5pro_information.py" for i in range(1, 5)},
    "P1-O01": "test_w5pro_planner.py", "P1-O02": "test_w5pro_planner.py",
    "P1-O04": "test_w5pro_planner.py",
    "P1-G12": "test_q4_w5pro_geometry_sweep.py",
}
KEYWORDS = {
    "baseline": "w5_policy.py", "identity": "w5pro_config.py", "hypothesis": "w5pro_hypothesis.py",
    "certificate": "w5pro_triangle_certificate.py", "triangle": "w5pro_triangle_certificate.py",
    "backbone": "w5pro_backbone.py", "NBV": "w5pro_nbv.py", "candidate": "w5pro_nbv.py",
    "RemainingTask": "w5pro_tasks.py", "task pool": "w5pro_tasks.py", "starvation": "w5pro_tasks.py",
    "SpatialStop": "w5pro_spatial.py", "future cost": "w5pro_future_cost.py", "planner": "w5pro_planner.py",
    "scheduler": "w5pro_scheduler.py", "ScanSession": "w5pro_scheduler.py", "CLEAR": "w5pro_clear.py",
    "Route Repair": "w5pro_route_repair.py", "intersection": "w5pro_nbv.py", "fallback": "w5pro_tail_fallback.py",
    "metrics": "w5pro_metrics.py", "误差场": "w5pro_experiment_matrix.py",
    # Explicit W5Pro implementation vocabulary (the checklist is bilingual,
    # so English-only matching leaves many real mappings falsely unmapped).
    "25 点": "w5_geometry.py", "25个点": "w5_geometry.py", "三角形拓扑": "w5pro_triangle_certificate.py",
    "合法三角形": "w5pro_triangle_certificate.py", "连续覆盖": "w5pro_triangle_certificate.py",
    "GlobalMapMaturity": "w5pro_scheduler.py", "全局地图": "w5pro_scheduler.py",
    "部分 anchor": "w5pro_backbone.py", "anchor 排序": "w5pro_backbone.py",
    "positive bearing": "w5pro_hypothesis.py", "effective region": "w5pro_hypothesis.py",
    "NO_SIGNAL": "w5pro_hypothesis.py", "频道 PRESENT": "w5pro_triangle_certificate.py",
    "backlog pressure": "w5pro_tasks.py", "nonlinear age": "w5pro_tasks.py",
    "novelty penalty": "w5pro_nbv.py", "crossing-angle": "w5pro_nbv.py",
    "TSPN": "w5pro_tspn.py", "route opportunity": "w5pro_corridor.py",
    "progress signature": "w5pro_safety.py", "action signature": "w5pro_safety.py",
    "Pareto prune": "w5pro_planner.py", "top-K": "w5pro_planner.py",
    "outcome probability": "w5pro_outcome.py", "CVaR": "w5pro_future_cost.py",
    "side sweep": "w5pro_geometry_sweep.py", "cap_extension sweep": "w5pro_geometry_sweep.py",
}


def build(documents: list[str | Path], root: str | Path) -> list[dict[str, str]]:
    root = Path(root)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for document in documents:
        text = Path(document).read_text(encoding="utf-8")
        for match in map(ITEM.match, text.splitlines()):
            if not match:
                continue
            key, title = match.group(1), " ".join(match.group(2).split())
            if key in seen:
                continue
            seen.add(key)
            context = text[max(0, match.start() - 180):match.end() + 260]
            module_names = sorted(set(MODULE.findall(context)))
            for keyword, filename in KEYWORDS.items():
                if keyword.lower() in (title + " " + context).lower():
                    module_names.append(filename)
            module_names = sorted(set(module_names))
            if key in ID_MODULES:
                module_names.append(ID_MODULES[key])
                module_names = sorted(set(module_names))
            existing = [name for name in module_names if (root / "q4" / name).is_file()]
            tests = sorted(p.name for p in (root / "offline_sim").glob("test_w5pro*.py")
                           if any(token.lower() in p.read_text(encoding="utf-8").lower()
                                  for token in (key.lower(), title.lower().split()[0])))
            if key in CONTRACT_TEST_IDS and (root / "offline_sim" / "test_w5pro_checklist_contract.py").is_file():
                tests.append("test_w5pro_checklist_contract.py")
                tests = sorted(set(tests))
            if key in EXPLICIT_TESTS and (root / "offline_sim" / EXPLICIT_TESTS[key]).is_file():
                tests.append(EXPLICIT_TESTS[key])
                tests = sorted(set(tests))
            if existing and tests:
                status = "code_and_test_candidate"
            elif existing:
                status = "code_candidate_only"
            else:
                status = "unmapped_or_runtime_only"
            rows.append({"id": key, "title": title, "status": status,
                         "modules": ";".join(existing), "tests": ";".join(tests),
                         "source": str(document)})
    return rows


def write_report(documents: list[str | Path], root: str | Path,
                 output: str | Path) -> Path:
    rows = build(documents, root)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "title", "status", "modules", "tests", "source"])
        writer.writeheader(); writer.writerows(rows)
    return output


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    docs = [
        Path(r"C:\Users\14535\.codex\attachments\fa9ea29d-0df4-476b-86de-f949de640405\pasted-text-1.txt"),
        Path(r"C:\Users\14535\.codex\attachments\fa9ea29d-0df4-476b-86de-f949de640405\pasted-text-2.txt"),
    ]
    target = root / "results" / "q4" / "w5pro_checklist_audit.csv"
    write_report(docs, root, target)
    print(target)
