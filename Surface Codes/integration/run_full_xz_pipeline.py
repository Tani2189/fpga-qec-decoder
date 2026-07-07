"""

Standalone Stim + PyMatching pipeline for FULL X+Z decoding of the
rotated distance-3 surface code.

This is intentionally separate from run_x_cpu_pipeline.py / run_fpga_pipeline.py:
those use the hand-built Qiskit circuits and are X-error only (validated via
their own Monte Carlo curve). This script uses Stim for CORRECT logical state
preparation, enabling both X and Z decoding side by side.

Examples
--------
# Single summary report, both bases, light noise
python -m integration.run_full_xz_pipeline --noise 0.01 --shots 20000

# Just one basis
python -m integration.run_full_xz_pipeline --basis Z --noise 0.01

# Full noise sweep + comparison plot (the verification curve)
python -m integration.run_full_xz_pipeline --sweep --save-plot
"""

import argparse
import time

import numpy as np

from surface_code.stim_circuits import (
    make_memory_circuit,
    sample_detection_events,
    build_matching,
)


# ============================================================
# Core decode-and-measure for a single basis / noise level
# ============================================================
def run_basis(basis, distance, rounds, noise, shots, seed=1):
    """
    Build circuit, decode `shots` samples, return a result dict.
    """
    circuit = make_memory_circuit(
        basis=basis, distance=distance, rounds=rounds, noise=noise
    )
    matching = build_matching(circuit)

    t0 = time.perf_counter()
    events, obs = sample_detection_events(circuit, shots=shots, seed=seed)
    t1 = time.perf_counter()
    predictions = matching.decode_batch(events)
    t2 = time.perf_counter()

    failures = (predictions != obs).any(axis=1)
    logical_error_rate = failures.mean()

    return {
        "basis": basis,
        "distance": distance,
        "rounds": rounds,
        "noise": noise,
        "shots": shots,
        "num_detectors": events.shape[1],
        "detector_fire_rate": events.mean(),
        "logical_error_rate": logical_error_rate,
        "num_failures": int(failures.sum()),
        "sample_time_s": t1 - t0,
        "decode_time_s": t2 - t1,
        "decode_time_per_shot_us": (t2 - t1) / shots * 1e6,
    }


# ============================================================
# Report (single run, one or both bases)
# ============================================================
def print_report(results):
    print("=" * 70)
    print("Stim + PyMatching QEC Pipeline  (full X+Z decoding)")
    print("=" * 70)
    print()

    for r in results:
        print(f"Basis {r['basis']}")
        print(f"  Code                 : distance-{r['distance']} rotated surface code")
        print(f"  Rounds               : {r['rounds']}")
        print(f"  Noise (all channels) : {r['noise']}")
        print(f"  Shots                : {r['shots']}")
        print(f"  Detectors            : {r['num_detectors']}")
        print(f"  Detector fire rate   : {r['detector_fire_rate']:.4f}")
        print(f"  Logical error rate   : {r['logical_error_rate']:.4f} "
              f"({r['num_failures']}/{r['shots']} shots)")
        print(f"  Decode time / shot   : {r['decode_time_per_shot_us']:.2f} us")
        print()

    print("Note")
    print("  State preparation is handled by Stim (correct by construction),")
    print("  unlike the Qiskit-based CPU/FPGA pipeline, which is X-error only")
    print("  because its data qubits start in bare |0> (not a valid X-stabilizer")
    print("  eigenstate). This script is the X+Z-capable path; the CPU/FPGA")
    print("  pipeline remains the validated, benchmarked X-only hardware path.")


# ============================================================
# Sweep mode: the actual verification curve
# ============================================================
def run_sweep(distance, rounds, shots, noise_levels, save_plot=False):
    print("=" * 70)
    print("Stim + PyMatching: Logical Error Rate vs Noise (both bases)")
    print("=" * 70)
    print(f"distance={distance}  rounds={rounds}  shots={shots}\n")

    results = {"Z": [], "X": []}

    for basis in ("Z", "X"):
        print(f"--- Basis {basis} ---")
        for noise in noise_levels:
            r = run_basis(basis, distance, rounds, noise, shots)
            results[basis].append(r["logical_error_rate"])
            print(f"  noise={noise:7.4f}   logical_error_rate={r['logical_error_rate']:.4f}")
        print()

    print("Sanity checks")
    for basis in ("Z", "X"):
        rates = results[basis]
        monotonic = all(rates[i] <= rates[i + 1] for i in range(len(rates) - 1))
        print(f"  Basis {basis}: monotonic with noise = {monotonic}, "
              f"lowest-noise rate = {rates[0]:.4f}")

    if save_plot:
        path = save_sweep_plot(noise_levels, results, distance, rounds, shots)
        print(f"\nSaved plot: {path}")

    return results


def save_sweep_plot(noise_levels, results, distance, rounds, shots):
    import os
    from datetime import datetime
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs("results/stim", exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(noise_levels, results["Z"], marker="o", label="Z basis (X-error decoding)")
    ax.plot(noise_levels, results["X"], marker="s", label="X basis (Z-error decoding)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Physical noise strength (log scale)")
    ax.set_ylabel("Logical error rate (log scale)")
    ax.set_title(f"Logical Error Rate vs Noise\n"
                 f"distance-{distance}, {rounds} rounds, {shots} shots/point")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)

    path = f"results/stim/logical_error_sweep_{stamp}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Stim + PyMatching X+Z QEC decoding pipeline."
    )
    parser.add_argument("--basis", choices=["Z", "X", "both"], default="both")
    parser.add_argument("--distance", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--noise", type=float, default=0.01)
    parser.add_argument("--shots", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=1)

    parser.add_argument("--sweep", action="store_true",
                        help="Run a noise sweep instead of a single report.")
    parser.add_argument("--save-plot", action="store_true",
                        help="Save the sweep comparison plot (only with --sweep).")

    args = parser.parse_args()

    if args.sweep:
        noise_levels = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05]
        run_sweep(args.distance, args.rounds, args.shots, noise_levels,
                  save_plot=args.save_plot)
        return

    bases = ["Z", "X"] if args.basis == "both" else [args.basis]
    results = [
        run_basis(b, args.distance, args.rounds, args.noise, args.shots, args.seed)
        for b in bases
    ]
    print_report(results)


if __name__ == "__main__":
    main()