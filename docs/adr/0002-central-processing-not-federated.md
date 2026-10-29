# Central processing, federation designed but not built

Status: accepted for the hackathon (deadline under 24 hours).

The access body processes all data in one central analysis store. A federated mode was designed (one node per data holder, the central body sends the compiled plan, nodes return only aggregates) but not built.

The data shows that federation would give the same numbers:

- Every encounter is held by the same hospital as its patient (0 of 47,706 differ).
- Every measure the compiler produces can be split up: counts and distinct patient counts are sums over disjoint partitions, a mean is sum ×10 divided by n, and "latest value per patient" never crosses a hospital.
- Merging the node aggregates and then applying the small-cell gate centrally would therefore give exactly the central result.
- The differencing check could also stay node-local: |A Δ B| is the sum of the per-node symmetric differences.

## Considered options

- **Central only (chosen):** one store, and the metrics and tests already cover it.
- **Federated nodes:** more realistic for the EHDS (the hospitals keep the data), but it needs a node API, plan serialisation, aggregate merging and the same test suite run in both modes. There was no time for that.

## Consequences

The README states that federation is not implemented. If it is built later, the existing golden and oracle tests are the acceptance test: both modes must give identical results on all 29 requests.
