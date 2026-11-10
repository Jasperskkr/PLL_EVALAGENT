# Optional nonideal model 1.0

Generated extension of original kernel.cpp, with original file unchanged. `generate_stage6c_kernel.py` asserts exact substitution locations, emits stage6c_kernel.cpp including original simulate. Build identity binds original, generated, generator, Python adapter, identity tool and DLL; no stale fallback. If all extension effects zero, direct dispatch to original simulate, with exact traces/edges.

Still fixed time grid + within-step edge interpolation + explicit Euler LF, not exact adaptive event integration. f=f0+KvcoV+K2V(V−V*); V* original linear tuning point. Both f(0)=f0 and f(V*)=80MHz; monotone positive throughout rails required, actual bracketed root and local derivative reported. Original ideal M1 ignores active terms explicitly, no bypass of original UNSUPPORTED.

CP pulse amplitudes Iup=Icp(1+δ/2), Idown=Icp(1−δ/2), times optional positive (1+a(V−V*)). Each step segments at actual interpolated reference/divider edges and scheduled reset. Both UP and DOWN remain on for reset_delay then reset; real simultaneous pulse charge is integrated. Explicit leakage positive into LF. No arbitrary mismatch offset current. Source pulses, charge, duty and reset count recorded. Passive branch=(v−u−eR)/R, C1dv=(I−branch)dt, C2du=branch dt, branch charges opposite; clamp loss separately accumulated. VCO phase integrates actual f each step. Reject nonmonotonic/invalid phases, no silent edge repair.

Adapter reuse in original experiments.py is only optional `simulate_fn` dispatch; original protocol/fit/sweeps/refinements/quality thresholds unchanged. It is not a second verifier. Single mechanisms, signs, dt, pulse charge, reset overlap, rails, phase law and capture checked independently before stochastic experiment claims.
