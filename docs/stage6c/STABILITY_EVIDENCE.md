# Phase D: two separate stability interfaces

M1: original continuous model supplies PM/UGF, strict Routh condition and cubic characteristic. Optional verifier reports complex poles of the same cubic for diagnosis; the real parts must be negative. This is the ideal nominal locked continuous model and explicitly ignores K2/mismatch/reset/leakage. It is not sampled periodic PM.

M2: PhaseB nonideal_02 independently measured paired-dt cold capture from0.15V/160us and finite5cycle0.4rad100kHz reference phase perturbation at50us ending100us with recovery observed to200us. Allfive tested profiles passed the declared capture/recovery; all response sweeps passed original halfamplitude/halfstep/doublewindow tests. Additional positive/negative mechanisms andrails/sourcecharge checked by17tests/independentglobal-eventoracle. Evidence is conditional on testedcandidate, fixedinitialcondition, excitation and finitewindow. No automaticextension to allinitialstates or wholeparameterdomain.

Noise tracking1.1: independent warmup oldcapture plus finiteobserved phase/control/rails/slip and halfwindowmeanfreq checks, statisticalnoise estimates separate from deterministic capturetime. Protocol1.0misclassification remains UNKNOWN in historicalresults. No claim exactglobalstability from this change.

Strict periodic PM/Floquet: UNKNOWN, notimplemented. No filledM2PMvalue, noM1PMconvertedtoM2PASS. FulloriginalSystemSpec includingmicrohertzprecision remains uncertified. Jointresearchfeasibility can only combine explicitM1PM with individually measuredM2BW/capture/recovery/jitter and valid profiles.
