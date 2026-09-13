"""Build a conservative, reproducible W5Pro checklist evidence report."""
from __future__ import annotations
import csv, json
from pathlib import Path

def build(root: Path, audit_path: Path) -> list[dict[str, str | int]]:
    rows = list(csv.DictReader(audit_path.open(encoding="utf-8")))
    hard_dirs = [p for p in (root / "results" / "q4").glob("w5pro_*hard*") if (p / "details.csv").is_file()]
    episodes = successes = 0
    for directory in hard_dirs:
        with (directory / "details.csv").open(encoding="utf-8", newline="") as stream:
            details = list(csv.DictReader(stream))
        episodes += len(details); successes += sum(row.get("success") == "1" for row in details)
    note = f"{successes}/{episodes} hard episodes in shared matrix; not an item-level proof" if hard_dirs else "none"
    baseline = root / "results" / "q4" / "w5_baseline_7case"
    baseline_ok = all((baseline / name).is_file() for name in ("details.csv", "summary.csv", "metadata.json"))
    paired = root / "results" / "q4" / "w5pro_paired_7case_final" / "paired_comparison.csv"
    paired_ok = paired.is_file() and sum(1 for _ in paired.open(encoding="utf-8")) == 8
    output = []
    for row in rows:
        item_runtime = int((baseline_ok and row["id"] == "P0-005") or
                           (paired_ok and row["id"] == "P0-006"))
        output.append({**row, "code_evidence": int(bool(row.get("modules"))),
                       "test_evidence": int(bool(row.get("tests"))),
                       "item_runtime_evidence": item_runtime,
                       "shared_runtime_evidence": int(bool(hard_dirs)), "runtime_note": note})
    return output

def write(root: Path, output: Path) -> Path:
    rows = build(root, root / "results" / "q4" / "w5pro_checklist_audit.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    missing = [r["id"] for r in rows
               if not r["test_evidence"] and not r["item_runtime_evidence"]]
    output.with_suffix(".summary.json").write_text(json.dumps({
        "items": len(rows), "code": sum(r["code_evidence"] for r in rows),
        "tests": sum(r["test_evidence"] for r in rows),
        "item_runtime": sum(r["item_runtime_evidence"] for r in rows),
        "missing_item_evidence_ids": missing,
        "strict_pass": not missing,
        "shared_runtime_note": rows[0]["runtime_note"] if rows else "none"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return output

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(write(root, root / "results" / "q4" / "w5pro_evidence_report.csv"))
