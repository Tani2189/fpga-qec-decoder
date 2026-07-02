"""
CPU QEC decoding pipeline (lookup, MWPM, full).

Examples
--------
python -m integration.run_cpu_pipeline --decoder cpu_mwpm --error X --qubit 4
python -m integration.run_cpu_pipeline --decoder full --error X --qubit 4
python -m integration.run_cpu_pipeline --decoder cpu_lookup --errors X1,X4
"""

import argparse
import random
import time

from surface_code.circuit_builder import build_single_round_circuit
from surface_code.syndrome_generator import (
    get_syndrome, get_syndrome_int, get_full_syndrome,
)
from surface_code.error_parser import parse_error_string
from cpu_decoder.lookup_decoder import decode as cpu_lookup_decode
from cpu_decoder.mwpm_decoder import decode as cpu_mwpm_decode
from cpu_decoder.full_decoder import decode_full

from integration.common import (
    surface_code_geometry, save_text_report, save_circuit_image, build_report,
)


def run_cpu_lookup(syndrome_bitstring):
    return cpu_lookup_decode(syndrome_bitstring)


def run_cpu_mwpm(syndrome_bitstring):
    correction_vector = cpu_mwpm_decode(syndrome_bitstring)
    qubits = [q for q, b in enumerate(correction_vector) if b]
    return qubits if qubits else None


def get_decoder_description(decoder_arg):
    return {
        "cpu_lookup": ("CPU Lookup Decoder", "CPU"),
        "cpu_mwpm": ("CPU MWPM Decoder", "CPU"),
        "full": ("Full Dual Decoder (X only; Z is placeholder)", "CPU"),
    }.get(decoder_arg, (decoder_arg, "Unknown"))


def main():
    parser = argparse.ArgumentParser(description="Run CPU QEC decoding pipeline.")
    parser.add_argument("--decoder",
                        choices=["cpu_lookup", "cpu_mwpm", "full"],
                        default="cpu_mwpm")
    parser.add_argument("--error", choices=["X", "Y", "Z"], default="X")
    parser.add_argument("--distance", type=int, default=3)
    parser.add_argument("--qubit", type=int, default=4)
    parser.add_argument("--random-error", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--save-circuit", action="store_true")
    parser.add_argument("--errors", type=str, default=None,
                        help="Multiple errors. Example: X1,Z4,Y7")
    args = parser.parse_args()

    if args.distance != 3:
        raise NotImplementedError("Only distance-3 surface code is implemented.")

    multi_errors = parse_error_string(args.errors) if args.errors else None

    if args.random_error:
        if args.seed is not None:
            random.seed(args.seed)
        args.qubit = random.randint(0, 8)
        args.error = random.choice(["X", "Y", "Z"])
        print(f"[Random Error] {args.error} on data qubit {args.qubit}")

    active_errors = multi_errors if multi_errors is not None \
        else [(args.error, args.qubit)]

    geometry = surface_code_geometry(args.distance)
    qc = build_single_round_circuit(errors=active_errors)

    syndrome_bitstring = get_syndrome(errors=active_errors)
    syndrome_int = get_syndrome_int(errors=active_errors)
    full_info = get_full_syndrome(errors=active_errors)

    results = {}
    start = time.perf_counter()

    if args.decoder == "cpu_lookup":
        results["cpu_lookup"] = run_cpu_lookup(syndrome_bitstring)
    elif args.decoder == "cpu_mwpm":
        results["cpu_mwpm"] = run_cpu_mwpm(syndrome_bitstring)
    elif args.decoder == "full":
        results["cpu_full"] = decode_full(
            error_qubit=args.qubit, error_type=args.error)

    elapsed_us = (time.perf_counter() - start) * 1e6

    decoder_name, hardware_name = get_decoder_description(args.decoder)
    report = build_report(args, geometry, active_errors, syndrome_bitstring,
                          syndrome_int, full_info, results, decoder_name,
                          hardware_name, elapsed_us)
    print(report)

    if args.save_report:
        print(f"\nSaved report to: {save_text_report(report)}")
    if args.save_circuit:
        print(f"Saved circuit image to: {save_circuit_image(qc)}")


if __name__ == "__main__":
    main()