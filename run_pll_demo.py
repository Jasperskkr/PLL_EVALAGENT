"""Run the minimal Python behavioral Integer-N CPPLL prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from v1.model.pll_behavioral import CPPLLParams, VCOParams, simulate_cppll, write_result


def _format_metric(value: object) -> str:
    if value is None:
        return "not locked"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="results/python_pll_demo.json",
        help="JSON result path (default: results/python_pll_demo.json)",
    )
    args = parser.parse_args()

    result = simulate_cppll(CPPLLParams(), VCOParams())
    write_result(result, args.output)

    print("Model:", result["model"])
    print("Mode:", result["mode"])
    print("Locked:", result["locked"])
    print("Simulation cycles:", result["simulation_cycles"])
    print("Output frequency (GHz):", _format_metric(result["metrics"]["output_frequency_hz"] / 1e9))
    print("Lock time (us):", _format_metric(None if result["metrics"]["lock_time_s"] is None else result["metrics"]["lock_time_s"] * 1e6))
    print("Integrated jitter (fs):", _format_metric(result["metrics"]["integrated_jitter_s"] * 1e15))
    print("Final VCO control (V):", _format_metric(result["metrics"]["final_vctrl_v"]))
    print("Result:", Path(args.output).resolve())


if __name__ == "__main__":
    main()
