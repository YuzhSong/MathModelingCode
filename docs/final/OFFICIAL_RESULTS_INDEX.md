# Official Results Index

## Current status

The Windows-prepared `official_results/` directory is now present in this Mac checkout. It was pulled from the remote branch; no official CSV or `.jlog` was fabricated, edited, renamed or inferred from offline runs.

Expected structure after the Windows materials are copied to the repository root:

```text
official_results/
├── q3/{practice,formal,q3_formal_summary.csv,README.md}
└── q4/{practice,formal,q4_formal_summary.csv,README.md}
```

## Required final checks

| Problem | Required formal runs | Required summary |
|---|---:|---|
| Q3 | exactly 3 | `official_results/q3/q3_formal_summary.csv` |
| Q4 | exactly 3 | `official_results/q4/q4_formal_summary.csv` |

Each formal row must contain a case ID and the four table fields: cleared source count, average localization-and-clear time, and real program runtime; the raw validation also requires `total_virtual_time_s`, `avg_time_per_cleared_s`, and `clear_fail_count`.

The consistency rule is:

```text
avg_time_per_cleared_s = total_virtual_time_s / cleared_count
```

`program_real_time_s` must be measured from successful `/enter` to `/exit` in real time. It must not be substituted with virtual time or an ordinary logger wall-time field.

## Provenance and .jlog policy

Official encrypted `.jlog` files must remain byte-for-byte unchanged if retained locally. For a public GitHub repository, prefer committing the formal summaries, README files, and this index only; keep encrypted `.jlog` files in the local competition submission materials unless publication is explicitly required.

Validation completed: Q3 has exactly 3 formal rows and 3 formal `.jlog` files; Q4 has exactly 3 formal rows and 3 formal `.jlog` files. All required fields are present, all average-time identities pass, and all manifest file sizes/SHA-256 values match. Do not mix official rows into offline CSVs.
