# Conference snapshot claim-to-evidence register

The immutable PDF is a historical five-seed report. This register maps every
substantive claim group to public evidence and records qualifications found by
the source audit. Machine-readable entries are in
[`claims-evidence.json`](claims-evidence.json); known corrections are in
[`ERRATA.md`](ERRATA.md).

| Claim ID | PDF location | Claim group | Status | Primary evidence |
|---|---|---|---|---|
| `CS-MOD-01` | p. 2, (1) | Isothermal Steinmetz loss model | Supported | protocol audit; current tested implementation |
| `CS-MOD-02` | p. 2, (2) | Single-pole Cole–Cole permeability and inductance mapping | Supported | protocol audit; current tested implementation |
| `CS-SCOPE-01` | pp. 2–3, Table I | Temperature and operating cohorts | **Corrected** | protocol audit; [erratum 4](ERRATA.md) |
| `CS-STAT-01` | p. 2, (3)–(4) | Six transformed parameters, Gaussian likelihood and prior | Supported | protocol audit; configuration |
| `CS-STAT-02` | p. 2 | Noise/weighting scales | **Corrected** | protocol audit; [erratum 1](ERRATA.md) |
| `CS-MCMC-01` | pp. 2–3, Table I | 48 walkers, 1000 warm-up, 5000 retained and diagnostic gates | Supported | `default.toml`; source artifact index |
| `CS-FISH-METHOD-01` | p. 2, (5) | Local Fisher calculation and limited interpretation | Supported | historical summary and Fig. 1 |
| `CS-EIG-METHOD-01` | pp. 2–3, (6)–(7) | Nested EIG 300/100 and EIG-per-cost ranking | Qualified | configuration; protocol audit |
| `CS-EIG-SEED-01` | p. 3 | Candidate-list order cannot affect score | **Contradicted** | protocol audit; [erratum 2](ERRATA.md) |
| `CS-SEQ-01` | p. 3 | Shared candidate outcomes and deterministic balanced baseline | Supported | protocol audit; per-seed hashes |
| `CS-STOP-01` | pp. 3–5, Table I | 90% precision gate, 8%/5%, maximum 25 | **Qualified** | configuration; [erratum 3](ERRATA.md) |
| `CS-REP-01` | pp. 3–4 | Fixed settings, seeds and acceptance/exclusion gates | Supported | lock, configuration and source artifact index |
| `CS-RES-FISH-01` | pp. 3–4, Fig. 1a | Rank 6, eigenvalue range and condition number | Supported | `paper_summary.json`; Fig. 1 |
| `CS-RES-REC-01` | pp. 1, 3–5, Table II | Six recovery medians and 28/30 interval inclusion | Supported | `paper_summary.json`; frozen table; Fig. 1 |
| `CS-RES-EIG-01` | pp. 1, 3–5, Fig. 2a | `[5,6,5,5,6]` vs `[9,9,9,9,9]`, 5/5 wins, 40.0% | Supported historical | `paper_summary.json`; Fig. 2 |
| `CS-RES-MU-01` | pp. 1, 4–5, Fig. 2b | Accepted N87/N95 permeability RRMSEs | Supported | `paper_summary.json`; Fig. 2 |
| `CS-RES-MU-EXCL-01` | pp. 4–5 | N87 and 3C95 MagNet records excluded | Supported | `paper_summary.json`; source artifact index |
| `CS-RES-PCV-01` | pp. 1, 4–5, Fig. 2b | Four measured core-loss RRMSEs | Supported | `paper_summary.json`; Fig. 2 |
| `CS-INT-01` | pp. 1, 4–5 | Larger loss-permeability residual indicates one-pole inadequacy | Qualified interpretation | measured RRMSEs; stated model scope |
| `CS-LIM-01` | pp. 4–5 | Measured errors are in-sample; no holdout validation | Supported limitation | protocol audit; measured summary |
| `CS-LIM-02` | p. 5 | Five seeds and finite nested MC do not establish coverage/ranking stability | Supported limitation | seed inventory; cited literature |
| `CS-LIM-03` | p. 5 | Measurement count is not laboratory time | Supported limitation | modeled costs in protocol audit |
| `CS-LIT-01`–`05` | pp. 1–2, references | Background magnetic, Bayesian-design and diagnostic claims | Cited | [`references.bib`](references.bib) |

All quantitative values are read from the historical
[`paper_summary.json`](../../results/historical/20260806T112202Z_9a37bcc67637/tables/paper_summary.json),
not transcribed into this register as a second source of truth. Its SHA-256 is
`0fc603ecd0ca7e94696c35f48ef7001165a4b9211e74d214c599425755c4c095`.
