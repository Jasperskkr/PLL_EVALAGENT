def phase_to_timing(phase_deg, fref_Hz):
    return phase_deg / (360 * fref_Hz)


def charge_window(phase_deg, fref_Hz, I_up_A, I_down_A):
    dt = phase_to_timing(phase_deg, fref_Hz)
    return {"timing_limit_s": dt, "min_C": -I_up_A*dt, "max_C": I_down_A*dt,
            "definition": "q_balance_C_after_proxy_load", "unit": "C"}


def signed_charge(target, timing_s):
    return target["q0_C"] + (target["I_up_A"] if timing_s >= 0 else target["I_down_A"])*timing_s


def equilibrium_timing(target):
    return -target["q0_C"] / (target["I_up_A"] if target["q0_C"] <= 0 else target["I_down_A"])
