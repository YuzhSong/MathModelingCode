# Negative Results as Model-Selection Evidence

These experiments are preserved because they explain why RARC/V6 was selected. They are not implementation failures to be hidden.

1. **Local information only (V5-A/B/final).** Better one-step localization probability did not imply lower total route time. Local value and global multi-task movement were not equivalent.
2. **Deep lookahead (V6-L2).** Extra local rollout did not stably resolve long-horizon SEARCH/FOUND/CLEAR coupling and worsened tails.
3. **Ring-only center ablation.** The outer ring can satisfy coverage conditions for relevant n, but removing the center's early information did not guarantee lower total time; downstream localization movement can offset saved scans.
4. **Historical no_signal.** The information is mathematically valid and can produce small gains, but the aggregate effect is insufficient for replacement.
5. **SEARCH-backbone + bundle.** Fixing SEARCH relative order and inserting FOUND-source work over-constrained the rolling router. In the 200-case comparison it retained 100% clear but had Mean(T/N) 309.56 vs V6 278.69 s/source, P95 total 4869.16 vs 4244.83 s, and 113 regressions over 300 s.

The appropriate conclusion is not that these mechanisms are universally invalid; it is that, under this Q3 simulator, frozen candidate set, n=8, and evaluation protocol, they did not justify replacing V6.
