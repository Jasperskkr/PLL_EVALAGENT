import cmath
import math


def operators(Rz_Ohm, C1_F, C2_F, period_s):
    """Exact two-state passive RC transition and integral, one physical period."""
    total = C1_F+C2_F
    rate = total/(Rz_Ohm*C1_F*C2_F)
    lost = -math.expm1(-rate*period_s)
    decay = 1-lost
    transition = ((1-C2_F/total*lost, C2_F/total*lost),
                  (C1_F/total*lost, 1-C1_F/total*lost))
    area = lost/rate
    integral_row = (C1_F/total*period_s+C2_F/total*area,
                    C2_F/total*(period_s-area))
    return transition, integral_row


def impedance(Rz_Ohm, C1_F, C2_F, frequency_Hz):
    s = 2j*math.pi*frequency_Hz
    return (1+s*Rz_Ohm*C2_F)/(s*(C1_F+C2_F)+s*s*Rz_Ohm*C1_F*C2_F)


def requirements(target):
    r, c1, c2 = target["Rz_Ohm"], target["C1_F"]+target["Cload_F"], target["C2_F"]
    samples = []
    for f in (1e5, 1e6, 1e7):
        z = impedance(r, c1, c2, f)
        samples.append({"frequency_Hz": f, "magnitude_Ohm": abs(z), "phase_deg": math.degrees(cmath.phase(z))})
    return {"Rz_Ohm": r, "C1_F": target["C1_F"], "C2_F": c2, "C1_effective_F": c1,
            "proxy_Cload_F": target["Cload_F"], "proxy_Rload_Ohm": target["Rload_Ohm"],
            "zero_Hz": 1/(2*math.pi*r*c2), "nonzero_pole_Hz": (c1+c2)/(2*math.pi*r*c1*c2),
            "impedance_samples": samples, "measurement": "ideal_RC_small_signal_impedance",
            "relation": "(1+s*Rz*C2)/(s*(C1eff+C2)+s^2*Rz*C1eff*C2)",
            "proxy_scope": "50fF proxy is not measured VCO input admittance; Rload local DC demand is already in q0; incremental conductance omitted"}
