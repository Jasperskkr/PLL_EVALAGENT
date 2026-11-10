# M1 independent noise mapping 1.0

Owner physics_mapping/noise.py, external contract block_space/extensions.py. Original strict model.py is byte-preserved and supplies all nominal BW/PM/UGF and loop responses. Input complete original JointBlockSpec plus NoiseProfile 1.0 plus explicit positive integration band. Profiles are frozen research environments, never optimizer variables. Unsupported correlation, units, singular offsets or extrapolation raises an explicit domain/unsupported error; runner must turn it into UNKNOWN, never PASS.

At s=j2πf, K0=2πKvco, reuse L and Z from original M1. Href=NL/(1+L), Hvco=1/(1+L), Hcp=K0 Z/[s(1+L)], HR=K0 D_R/[s(1+L)], D_R=C2/(C1+C2+sRzC1C2). Phase rad; Hcp rad/A, HR rad/V; input one-sided PSD gives rad²/Hz at output. Series voltage eR uses branch=(v−u−eR)/R; independent KCL test solves both capacitor voltages and output phase with closed-loop feedback. 4kBTR is not added directly to control voltage PSD.

Single-sided conversion: positive-frequency two-sided PSD ×2. Small-angle SSB dBc/Hz → 2×10^(L/10) rad²/Hz. Reverse L=10log10(Sphi/2). Log-log interpolation only inside explicit table validity band; zero density represented as white=0. Sum phase variances then sqrt/(2πfout). Source time variances and fractional contributions reported. Finite log trapezoid integration is mesh-checked, not an infinite-band statement.

Transfer sensitivity freezes all source PSDs, including R thermal density at original R, and changes only transfer. A separate column includes known physical R thermal change. Other intrinsic source dependence is UNMODELED under frozen-source assumptions, not proven absent. Normalized log derivatives for Icp/Rz/Kvco/f0; C1/C2 require enumerated valid choices. Noise=0 still calls unchanged original nominal metrics, exact equality tested.

Evidence classification: supplied physical equations + independently solved nodal reference, not device calibration. Test pass does not validate noisy sampled PLL behavior; that is Phase C.
