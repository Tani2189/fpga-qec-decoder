"""
FPGA QEC decoding pipeline (PyXRT lookup decoder), with CPU comparison.

WARNING: the FPGA .xclbin must be synthesized from the CURRENT d=3 geometry.
A stale bitstream returns wrong corrections (e.g. -1 for valid syndromes).

Examples
--------
python -m integration.run_x_fpga_pipeline --error X --qubit 4
python -m integration.run_x_fpga_pipeline --error X --qubit 4 --no-compare
"""

import argparse
import random
import time
from pathlib import Path

import numpy as np

from surface_code.circuit_builder import build_single_round_circuit
from surface_code.syndrome_generator import (
    get_syndrome, get_syndrome_int, get_full_syndrome,
)
from surface_code.error_parser import parse_error_string
from cpu_decoder.lookup_decoder import decode as cpu_lookup_decode

from integration.common import (
    surface_code_geometry, save_text_report, save_circuit_image, build_report,
)

try:
    import pyxrt
    PYXRT_AVAILABLE = True
except ImportError:
    PYXRT_AVAILABLE = False


class FPGALookupDecoder:
    def __init__(self):
        if not PYXRT_AVAILABLE:
            raise RuntimeError("pyxrt not available. Source the XRT environment first.")
        repo_root = Path(__file__).resolve().parents[1]
        xclbin_path = repo_root / "fpga_decoder" / "build" / "fpga_lookup_decoder.xclbin"
        if not xclbin_path.exists():
            raise FileNotFoundError(f"xclbin not found: {xclbin_path}")

        self.device = pyxrt.device(0)
        self.xclbin = pyxrt.xclbin(str(xclbin_path))
        self.uuid = self.device.load_xclbin(self.xclbin)
        self.kernel = pyxrt.kernel(self.device, self.uuid, "qec_decoder")

        self.input_array = np.zeros(1, dtype=np.int32)
        self.output_array = np.zeros(1, dtype=np.int32)
        self.in_bo = pyxrt.bo(self.device, self.input_array.nbytes,
                              pyxrt.bo.normal, self.kernel.group_id(0))
        self.out_bo = pyxrt.bo(self.device, self.output_array.nbytes,
                               pyxrt.bo.normal, self.kernel.group_id(1))

    def decode(self, syndrome_int):
        self.input_array[0] = syndrome_int
        self.in_bo.write(self.input_array, 0)
        self.in_bo.sync(pyxrt.xclBOSyncDirection.XCL_BO_SYNC_BO_TO_DEVICE,
                        self.input_array.nbytes, 0)
        run = self.kernel(self.in_bo, self.out_bo, np.int32(1))
        run.wait()
        self.out_bo.sync(pyxrt.xclBOSyncDirection.XCL_BO_SYNC_BO_FROM_DEVICE,
                         self.output_array.nbytes, 0)
        data = self.out_bo.read(self.output_array.nbytes, 0)
        self.output_array = np.frombuffer(data, dtype=np.int32)
        return int(self.output_array[0])


def main():
    parser = argparse.ArgumentParser(description="Run FPGA QEC decoding pipeline.")
    parser.add_argument("--error", choices=["X", "Y", "Z"], default="X")
    parser.add_argument("--distance", type=int, default=3)
    parser.add_argument("--qubit", type=int, default=4)
    parser.add_argument("--random-error", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-compare", action="store_true",
                        help="Run FPGA only, skip CPU comparison.")
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

    for et, _ in active_errors:
        if et != "X":
            print("[WARNING] FPGA lookup decoder supports X-error decoding only.")
            break

    geometry = surface_code_geometry(args.distance)
    qc = build_single_round_circuit(errors=active_errors)

    syndrome_bitstring = get_syndrome(errors=active_errors)
    syndrome_int = get_syndrome_int(errors=active_errors)
    full_info = get_full_syndrome(errors=active_errors)

    fpga_decoder = FPGALookupDecoder()

    results = {}
    start = time.perf_counter()
    results["fpga_lookup"] = fpga_decoder.decode(syndrome_int)
    if not args.no_compare:
        results["cpu_lookup"] = cpu_lookup_decode(syndrome_bitstring)
        results["match"] = results["cpu_lookup"] == results["fpga_lookup"]
    elapsed_us = (time.perf_counter() - start) * 1e6

    if not args.no_compare:
        decoder_name = "CPU Lookup Decoder + FPGA Lookup Decoder"
        hardware_name = "CPU + Xilinx FPGA"
    else:
        decoder_name, hardware_name = "FPGA Lookup Decoder", "Xilinx FPGA"

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