# Q4 W5 symmetric 25-point geometry validation

The design contains the origin, six first-ring points, twelve second-ring points, and six outward cap points. Policy code receives only these fixed coordinates; simulator ground truth is used only by later offline evaluation.

## Analytical construction

The cap-apex constraint `a^2 + (1800-sqrt(3)a)^2 <= 1000^2` gives `a in [561.477916, 997.367811]m`; the upper root is independently computed rather than hard-coded.
Inside the second-ring hexagon, complete triangular cells have side `a<=1000m`, so each source is in the convex hull of three detectors within reception range. Each circular cap is split into two local triangles by its edge midpoint and outward supplement. The sloping supplement-to-vertex side must support the radius-1800 circle; this is checked by its distance from the origin.

## Parameter screen

| a m | p m | Analytic | Misses | Angular margin deg | Cap support margin m | Open route m |
| --- | --- | --- | --- | --- | --- | --- |
| 960 | 180 | 1 | 0 | 2.78 | 11.21 | 18443.65 |
| 970 | 140 | 1 | 0 | 0.38 | 1.42 | 18350.26 |
| 970 | 180 | 1 | 0 | 7.12 | 28.87 | 18622.80 |
| 980 | 120 | 1 | 0 | 1.27 | 3.94 | 18396.60 |
| 980 | 160 | 1 | 0 | 8.50 | 33.14 | 18664.88 |
| 990 | 100 | 1 | 0 | 1.94 | 5.54 | 18445.19 |
| 990 | 120 | 1 | 0 | 6.31 | 21.40 | 18576.23 |
| 990 | 160 | 1 | 0 | 10.15 | 50.72 | 18844.23 |
| 990 | 200 | 1 | 0 | 8.47 | 76.81 | 19120.00 |
| 995 | 100 | 1 | 0 | 4.65 | 14.25 | 18535.06 |
| 997 | 80 | 1 | 0 | 0.48 | 1.07 | 18445.23 |

Selected geometry for policy pilot: `a=970m`, `p=140m`, `rho=1820.089m`. It passed `204700` formal probes with zero misses; worst angular gap is `179.576302deg` and sampled worst visible distance is `975.305m`.

The historical hand candidate `a=990,p=200` is retained in the table and validated rather than assumed. Parameter selection is lexicographic: reject any analytic/numeric failure, then expose route length and safety margin separately. No weighted reward is used.

## Conditional minimum for the fixed 19-point skeleton

At adjacent outward cap apices, one detector satisfying both outward tangent half-planes has nearest possible distance `1039.230485m` to each apex, exceeding the 1000m reception radius. Therefore one added point cannot guarantee both adjacent outward cases. Six distinct caps require at least six supplements, so 25 is a lower bound conditional on retaining this fixed 19-point skeleton.

This is not a global proof that every possible detection geometry needs at least 25 points. It proves only the stated 19+cap construction minimum.

## Verification scope

The selected candidate is checked with one million fixed-seed random disk samples, dense sampling of all six caps, dense arena-boundary points, and triangular-cell edges. The angular-gap test covers every source direction at each sampled source position; sampled direction checks additionally report visible-distance behavior. Numeric zero miss supports the construction but is not presented as an independent formal proof over a continuum.
