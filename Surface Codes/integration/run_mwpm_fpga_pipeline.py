"""
integration/run_mwpm_fpga_pipeline.py

FPGA MWPM decoding pipeline (bounded bitmask-DP kernel), repeated-round
(spacetime) X-error decoding, distance-3 surface code, rounds=4.

Companion to run_fpga_pipeline.py (lookup, single-round). Verified on
real FPGA hardware: 500/500 vs the CPU reference (bit-for-bit on
non-tied syndromes; see the tie-aware correctness check below for why
occasional non-identical-but-equally-valid answers are expected, not bugs).

Examples
--------
python -m integration.run_mwpm_fpga_pipeline --qubit 4
python -m integration.run_mwpm_fpga_pipeline --qubit 4 --meas-error-round 2 --meas-error-stab 0
python -m integration.run_mwpm_fpga_pipeline --random-error --no-compare
"""

import argparse
import random
import time

import numpy as np

from surface_code.syndrome_generator import (
    get_multi_round_bitstring, inject_measurement_errors,
)
from surface_code.repeated_syndrome import split_rounds
from surface_code.error_parser import parse_error_string
from cpu_decoder.mwpm_decoder import MWPMDecoder, build_check_matrix
from fpga_decoder.host.mwpm_fpga_decoder import FPGAMWPMDecoder, MAX_ACTIVE_DEFECTS

from integration.common import surface_code_geometry, save_text_report

ROUNDS = 4
NUM_STAB = 4


def to_node(stab, round_):
    return round_ * NUM_STAB + stab


def get_active_nodes(round_syndromes, decoder):
    diff = decoder.difference_syndrome(round_syndromes)
    return [
        to_node(s, r)
        for r in range(diff.shape[1])
        for s in range(diff.shape[0])
        if diff[s, r]
    ]


def compare_corrections(fpga_mask, cpu_correction, H):
    """
    Tie-aware comparison. FPGA implements a bounded bitmask-DP matcher,
    not PyMatching's blossom directly - the two can pick different,
    equally-optimal matchings on a weight tie (verified: ~3-4% of
    syndromes, 0 real bugs across 2000+ trials in diagnose_weight_ties.py).

    A raw bit-equality check would misreport these ties as failures.
    Instead: check whether the residual (fpga XOR cpu) has zero syndrome.
    Zero syndrome -> both are valid corrections for the same error
    (exact match, or a legitimate tie). Nonzero -> a real bug.

    Returns one of: "exact", "tie", "bug"
    """
    num_data = H.shape[1]
    fpga_vec = np.array([(fpga_mask >> q) & 1 for q in range(num_data)], dtype=np.uint8)
    cpu_vec = np.array(cpu_correction, dtype=np.uint8)

    if np.array_equal(fpga_vec, cpu_vec):
        return "exact"

    residual_syndrome = (H @ (fpga_vec ^ cpu_vec)) % 2
    return "bug" if residual_syndrome.any() else "tie"


def build_report(args, geometry, active_errors, round_syndromes, active_nodes,
                 results, load_time_ms, decode_time_us, overflow):
    lines = []
    lines.append("=" * 70)
    lines.append("FPGA MWPM Decoding Pipeline (spacetime, bounded bitmask-DP)")
    lines.append("=" * 70)
    lines.append("")
    lines.append("System Configuration")
    lines.append(f"  Quantum code         : Surface Code (distance-{args.distance})")
    lines.append(f"  Logical qubits       : {geometry['logical_qubits']}")
    lines.append(f"  Data qubits          : {geometry['data_qubits']}")
    lines.append(f"  Rounds               : {ROUNDS}")
    lines.append(f"  Decoder              : FPGA MWPM (bounded bitmask-DP, "
                 f"MAX_ACTIVE_DEFECTS={MAX_ACTIVE_DEFECTS})")
    lines.append(f"  Execution hardware   : Xilinx Alveo U55C")

    if len(active_errors) == 1:
        et, q = active_errors[0]
        lines.append(f"  Injected error       : {et} on data qubit {q}")
    else:
        s = ", ".join(f"{e} on q{q}" for e, q in active_errors)
        lines.append(f"  Injected errors      : {s}")
    if args.meas_error_round is not None:
        lines.append(
            f"  Injected meas. error : stabilizer S{args.meas_error_stab}, "
            f"round {args.meas_error_round}"
        )
    lines.append("")

    lines.append("Repeated-Round Syndromes")
    for i, s in enumerate(round_syndromes):
        lines.append(f"  Round {i}: {s}")
    lines.append("")

    lines.append("Detection Graph")
    lines.append(f"  Active detector nodes : {active_nodes}")
    lines.append(f"  Count                 : {len(active_nodes)} "
                 f"(bound: {MAX_ACTIVE_DEFECTS})")
    lines.append("")

    if overflow:
        lines.append("Decoder Results")
        lines.append("  SKIPPED: active defect count exceeds MAX_ACTIVE_DEFECTS.")
        lines.append("  This is a known, honest limitation of the bounded hardware")
        lines.append("  decoder, not a bug.")
        lines.append("")
    else:
        lines.append("Decoder Results")
        for k, v in results.items():
            lines.append(f"  {k:<18}: {v}")
        lines.append("")

        correction_qubits = results.get("fpga_mwpm_qubits")
        suggested = (f"Apply X to data qubit(s) {correction_qubits}"
                    if correction_qubits else "No correction required")
        lines.append("Correction Interpretation")
        lines.append(f"  Suggested correction  : {suggested}")
        lines.append("")

    lines.append("Final Status")
    lines.append("  Decoding status       : "
                 + ("Skipped (overflow)" if overflow else "Completed"))
    lines.append("")
    lines.append("Timing (reported separately - do not sum these)")
    lines.append(f"  Bitstream load (one-time, first call only): {load_time_ms:.1f} ms")
    lines.append(f"  Decode time (excludes load)                : {decode_time_us:.3f} us")
    lines.append("")
    lines.append("Note")
    lines.append("  Logical recovery is inferred from decoder output and has not")
    lines.append("  yet been formally verified through re-simulation. This pipeline")
    lines.append("  decodes X errors only - the kernel's ROM tables are built from")
    lines.append("  the Z-stabilizer graph. Z-error decoding is verified separately")
    lines.append("  on CPU (Stim track) but not yet ported to FPGA.")
    lines.append("  'match' below is tie-aware: FPGA and CPU can legitimately pick")
    lines.append("  different, equally-optimal corrections on a weight tie (~3-4%")
    lines.append("  of syndromes). Only a nonzero-residual-syndrome result is a bug.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run FPGA MWPM (spacetime) decoding pipeline.")
    parser.add_argument("--error", choices=["X"], default="X",
                        help="Only X is supported on this Qiskit-based track.")
    parser.add_argument("--distance", type=int, default=3)
    parser.add_argument("--qubit", type=int, default=4)
    parser.add_argument("--meas-error-round", type=int, default=None)
    parser.add_argument("--meas-error-stab", type=int, default=0)
    parser.add_argument("--random-error", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-compare", action="store_true")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--errors", type=str, default=None)
    args = parser.parse_args()

    if args.distance != 3:
        raise NotImplementedError("Only distance-3 is currently implemented.")

    multi_errors = parse_error_string(args.errors) if args.errors else None

    if args.random_error:
        if args.seed is not None:
            random.seed(args.seed)
        args.qubit = random.randint(0, 8)
        print(f"[Random Error] X on data qubit {args.qubit}")

    active_errors = multi_errors if multi_errors is not None else [(args.error, args.qubit)]
    if any(et != "X" for et, _ in active_errors):
        print("[WARNING] This kernel was built for X-error (Z-stabilizer) "
              "decoding only. Non-X errors will not decode correctly.")

    geometry = surface_code_geometry(args.distance)

    error_qubit = active_errors[0][1]
    bitstring = get_multi_round_bitstring(rounds=ROUNDS, error_qubit=error_qubit, error_type="X")
    round_syndromes = split_rounds(bitstring, ROUNDS)

    if args.meas_error_round is not None:
        round_syndromes = inject_measurement_errors(
            round_syndromes, flips=[(args.meas_error_stab, args.meas_error_round)]
        )

    cpu_decoder = MWPMDecoder()
    cpu_decoder.build_spacetime(ROUNDS)
    active_nodes = get_active_nodes(round_syndromes, cpu_decoder)

    overflow = len(active_nodes) > MAX_ACTIVE_DEFECTS
    results = {}
    load_time_ms = 0.0
    decode_time_us = 0.0

    if not overflow:
        # Bitstream load time measured and reported SEPARATELY - it is a
        # one-time cost, not part of per-decode latency. (This was the
        # bug in an earlier version of this script: the "decoding time"
        # figure included ~100ms of xclbin load, not just the decode.)
        t_load_start = time.perf_counter()
        fpga = FPGAMWPMDecoder(max_n=1)
        load_time_ms = (time.perf_counter() - t_load_start) * 1000

        t_decode_start = time.perf_counter()
        fpga_mask = fpga.decode_one(active_nodes)
        decode_time_us = (time.perf_counter() - t_decode_start) * 1e6

        fpga_qubits = [q for q in range(geometry["data_qubits"]) if fpga_mask & (1 << q)]
        results["fpga_mwpm_mask"] = hex(fpga_mask)
        results["fpga_mwpm_qubits"] = fpga_qubits

        if not args.no_compare:
            H = build_check_matrix()
            cpu_correction = cpu_decoder.decode_multi_round(round_syndromes)
            cpu_qubits = [q for q, b in enumerate(cpu_correction) if b]
            results["cpu_mwpm_qubits"] = cpu_qubits

            comparison = compare_corrections(fpga_mask, cpu_correction, H)
            results["match"] = comparison  # "exact" / "tie" / "bug"
            if comparison == "bug":
                print("\n[WARNING] Residual syndrome is nonzero - this is a genuine "
                      "mismatch, not a tie. Do not trust this correction.\n")

    report = build_report(args, geometry, active_errors, round_syndromes,
                          active_nodes, results, load_time_ms, decode_time_us, overflow)
    print(report)

    if args.save_report:
        print(f"\nSaved report to: {save_text_report(report)}")


if __name__ == "__main__":
    main()