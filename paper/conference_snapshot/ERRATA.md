# Conference snapshot errata and qualifications

The conference PDF is retained byte-for-byte as a historical artifact. The
following corrections are required when reading it.

1. **Noise-scale sentence, page 2.** A percent sign was interpreted as a TeX
   comment, truncating the rendered sentence. The implemented synthetic relative
   scales were 3% for core loss, 2% for real permeability, 5% for loss
   permeability, and 1% for inductance. Measured fits used a 3% relative
   weighting model. See [`protocol_audit.json`](../../results/historical/20260806T112202Z_9a37bcc67637/protocol/protocol_audit.json).

2. **Candidate-order invariance, pages 2–3.** The snapshot says that
   candidate-specific random streams make scores invariant to candidate-list
   order. The archived implementation seeded by candidate list index, so that
   statement is not supported for this historical run. The reported ranking and
   five-seed results remain the results of the recorded ordering; they are not an
   order-invariance demonstration.

3. **Stopping interval terminology, pages 3–5.** The archived stop calculation
   used the 5th and 95th percentiles of forward predictions over posterior
   parameter draws. It did not add new observation noise. The precise term is
   therefore a 90% posterior interval for the latent mean response, not a full
   posterior-predictive interval for a future noisy observation.

4. **Measured temperature cohort, pages 2–3 and Table I.** The single
   `25 ± 0.5 °C` description is correct for the synthetic candidate library but
   not for every measured fit. The accepted N87 permeability fit used a
   `25 ± 0.75 °C` selection, N95 permeability used `30 ± 0.75 °C`, the N49/N87/N95
   core-loss fits used `25 ± 0.5 °C`, and the 3C95 core-loss fit used
   `100 ± 0.5 °C`.

5. **Source provenance.** The exact binary has a fixed SHA-256 and all numeric
   claims map to the frozen historical work, but a byte-exact TeX source for the
   visible three-author conference build was not found in the archived work.
   This limits format-level reproducibility; it does not change the linked
   scientific result artifacts.

The five-seed acquisition result is descriptive historical evidence. The
[`current manuscript`](../current_state/manuscript.pdf) reports the current
benchmark and should be used for present scientific claims.
