# Conditional capture protocol audit

The existing cold-start pair is suitable for finite-window, fixed-initial-condition research after numerical convergence and deterministic repeatability are checked. It is not a global capture-domain or strict frequency-precision certificate.

The unchanged kernel initializes both LF voltage states to 0.15 V, VCO phase to zero, reference phase to zero, and UP/DOWN to false. Both edge counters begin at one. The pair uses 160 us duration, .4/.2 ns integration and 20 ns records without a capture stimulus. A 1 us block is valid only with frequency error <=100 ppm, wrapped phase <=5 degrees, Vctrl range <=5 mV, no clamps, and no intra-block cycle-index changes. Capture requires at least ten terminal valid blocks; lock time is the first start after the final invalid block. Startup cycle slips do not preclude terminal capture.

Paired results must have the same capture status, frequency difference <=1 ppm, control difference <=0.1 mV, and lock-time difference <=2 us when measured. The planned research deadline hull includes both steps and 1 us block resolution. A pair-converged noncapture is finite-window negative evidence, not an absolute impossibility. No kernel, thresholds or definitions were changed.

See capture_protocol_review.json for source hashes. Stage 6A candidate M2 has not been run at this setup gate.
