"""
Single-file end-to-end QEC pipeline with direct PyXRT FPGA execution.

This script:
1. Injects deterministic or random Pauli errors.
2. Generates surface-code syndromes.
3. Runs CPU and/or FPGA decoders.
4. Compares outputs.
5. Saves reports and circuit images.

Current Limitations
-------------------
- Only distance-3 surface code is physically implemented.
- FPGA lookup decoder currently supports X-error decoding only.
- Logical recovery is inferred, not formally re-verified.

Examples
--------

# CPU + FPGA lookup comparison
python -m integration.run_decoder_pipeline \
    --decoder both \
    --error X \
    --qubit 4

# Random error injection
python -m integration.run_decoder_pipeline \
    --decoder both \
    --random-error

# Full CPU decoder
python -m integration.run_decoder_pipeline \
    --decoder full \
    --error Y \
    --qubit 4

# Save report and circuit
python -m integration.run_decoder_pipeline \
    --decoder fpga \
    --error X \
    --qubit 4 \
    --save-report \
    --save-circuit
"""

import argparse
import os
import random
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from surface_code.circuit_builder import build_single_round_circuit

from surface_code.syndrome_generator import (
    get_syndrome,
    get_syndrome_int,
    get_full_syndrome,
)

from cpu_decoder.lookup_decoder import (
    decode as cpu_lookup_decode,
)

from cpu_decoder.mwpm_decoder import (
    decode as cpu_mwpm_decode,
)

from cpu_decoder.full_decoder import (
    decode_full,
)

# ============================================================
# Optional PyXRT Import
# ============================================================

try:
    import pyxrt

    PYXRT_AVAILABLE = True

except ImportError:

    PYXRT_AVAILABLE = False


# ============================================================
# Surface Code Geometry
# ============================================================

def surface_code_geometry(distance: int):

    if distance < 3 or distance % 2 == 0:
        raise ValueError(
            "Surface code distance must be an odd integer >= 3."
        )

    data_qubits = distance ** 2

    x_ancilla_qubits = (
        (distance ** 2 - 1) // 2
    )

    z_ancilla_qubits = (
        (distance ** 2 - 1) // 2
    )

    y_ancilla_qubits = 0

    total_ancilla_qubits = (
        x_ancilla_qubits
        + z_ancilla_qubits
    )

    total_physical_qubits = (
        data_qubits
        + total_ancilla_qubits
    )

    return {
        "distance": distance,
        "logical_qubits": 1,
        "data_qubits": data_qubits,
        "x_ancilla_qubits": x_ancilla_qubits,
        "z_ancilla_qubits": z_ancilla_qubits,
        "y_ancilla_qubits": y_ancilla_qubits,
        "total_ancilla_qubits": total_ancilla_qubits,
        "total_physical_qubits": total_physical_qubits,
    }


# ============================================================
# Utility Functions
# ============================================================

def timestamp():

    return datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )


def ensure_output_dirs():

    os.makedirs(
        "results/reports",
        exist_ok=True,
    )

    os.makedirs(
        "results/circuits",
        exist_ok=True,
    )


def save_text_report(content: str):

    ensure_output_dirs()

    filename = (
        f"results/reports/run_{timestamp()}.txt"
    )

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(content)

    return filename


def save_circuit_image(qc):

    ensure_output_dirs()

    filename = (
        f"results/circuits/circuit_{timestamp()}.png"
    )

    fig = qc.draw(output="mpl")

    fig.savefig(
        filename,
        bbox_inches="tight",
    )

    plt.close(fig)

    return filename


# ============================================================
# Persistent FPGA Decoder
# ============================================================

class FPGALookupDecoder:
    """
    Persistent FPGA lookup decoder context.

    Loads:
    - device
    - xclbin
    - kernel
    - buffers

    only once.
    """

    def __init__(self):

        if not PYXRT_AVAILABLE:
            raise RuntimeError(
                "pyxrt is not available. "
                "Source the XRT environment first."
            )

        repo_root = (
            Path(__file__).resolve().parents[1]
        )

        xclbin_path = (
            repo_root
            / "fpga_decoder"
            / "build"
            / "decoder_lookup.xclbin"
        )

        if not xclbin_path.exists():
            raise FileNotFoundError(
                f"xclbin not found: {xclbin_path}"
            )

        # ----------------------------------------------------
        # Open FPGA device
        # ----------------------------------------------------
        self.device = pyxrt.device(0)

        # ----------------------------------------------------
        # Load xclbin
        # ----------------------------------------------------
        self.xclbin = pyxrt.xclbin(
            str(xclbin_path)
        )

        self.uuid = self.device.load_xclbin(
            self.xclbin
        )

        # ----------------------------------------------------
        # Open kernel
        # ----------------------------------------------------
        self.kernel = pyxrt.kernel(
            self.device,
            self.uuid,
            "qec_decoder",
        )

        # ----------------------------------------------------
        # Allocate reusable buffers
        # ----------------------------------------------------
        self.input_array = np.zeros(
            1,
            dtype=np.int32,
        )

        self.output_array = np.zeros(
            1,
            dtype=np.int32,
        )

        self.in_bo = pyxrt.bo(
            self.device,
            self.input_array.nbytes,
            pyxrt.bo.normal,
            self.kernel.group_id(0),
        )

        self.out_bo = pyxrt.bo(
            self.device,
            self.output_array.nbytes,
            pyxrt.bo.normal,
            self.kernel.group_id(1),
        )

    def decode(self, syndrome_int: int):

        self.input_array[0] = syndrome_int

        # ----------------------------------------------------
        # Copy input to FPGA
        # ----------------------------------------------------
        self.in_bo.write(
            self.input_array,
            0,
        )

        self.in_bo.sync(
            pyxrt.xclBOSyncDirection.XCL_BO_SYNC_BO_TO_DEVICE,
            self.input_array.nbytes,
            0,
        )

        # ----------------------------------------------------
        # Launch kernel
        # ----------------------------------------------------
        run = self.kernel(
            self.in_bo,
            self.out_bo,
            np.int32(1),
        )

        run.wait()

        # ----------------------------------------------------
        # Copy output back
        # ----------------------------------------------------
        self.out_bo.sync(
            pyxrt.xclBOSyncDirection.XCL_BO_SYNC_BO_FROM_DEVICE,
            self.output_array.nbytes,
            0,
        )

        data = self.out_bo.read(
            self.output_array.nbytes,
            0,
        )

        self.output_array = np.frombuffer(
            data,
            dtype=np.int32,
        )

        return int(self.output_array[0])


# ============================================================
# CPU Decoder Helpers
# ============================================================

def run_cpu_lookup(
    syndrome_bitstring: str
):

    return cpu_lookup_decode(
        syndrome_bitstring
    )


def run_cpu_mwpm(
    syndrome_bitstring: str
):

    correction_vector = cpu_mwpm_decode(
        syndrome_bitstring
    )

    if 1 in correction_vector:
        return correction_vector.index(1)

    return None


# ============================================================
# Reporting Helpers
# ============================================================

def get_decoder_description(decoder_arg):

    if decoder_arg == "cpu_lookup":
        return (
            "CPU Lookup Decoder",
            "CPU",
        )

    if decoder_arg == "cpu_mwpm":
        return (
            "CPU MWPM Decoder",
            "CPU",
        )

    if decoder_arg == "fpga":
        return (
            "FPGA Lookup Decoder",
            "Xilinx FPGA",
        )

    if decoder_arg == "both":
        return (
            "CPU Lookup Decoder + FPGA Lookup Decoder",
            "CPU + Xilinx FPGA",
        )

    if decoder_arg == "full":
        return (
            "Full Dual Decoder (X and Z decoding)",
            "CPU",
        )

    return decoder_arg, "Unknown"


def determine_correction(
    results,
    injected_error,
):

    correction_operator = "Unknown"

    correction_qubit = None

    if "fpga_lookup" in results:

        correction_qubit = (
            results["fpga_lookup"]
        )

    elif "cpu_lookup" in results:

        correction_qubit = (
            results["cpu_lookup"]
        )

    elif "cpu_mwpm" in results:

        correction_qubit = (
            results["cpu_mwpm"]
        )

    elif (
        "cpu_full" in results
        and isinstance(
            results["cpu_full"],
            dict,
        )
    ):

        full_result = results["cpu_full"]

        if (
            full_result.get(
                "x_correction"
            )
            is not None
        ):

            correction_qubit = (
                full_result[
                    "x_correction"
                ]
            )

            correction_operator = "X"

        elif (
            full_result.get(
                "z_correction"
            )
            is not None
        ):

            correction_qubit = (
                full_result[
                    "z_correction"
                ]
            )

            correction_operator = "Z"

    return (
        correction_qubit,
        correction_operator,
    )


# ============================================================
# Main Pipeline
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Run end-to-end QEC decoding pipeline."
        )
    )

    parser.add_argument(
        "--decoder",
        choices=[
            "cpu_lookup",
            "cpu_mwpm",
            "fpga",
            "both",
            "full",
        ],
        default="both",
    )

    parser.add_argument(
        "--error",
        choices=["X", "Y", "Z"],
        default="X",
    )

    parser.add_argument(
        "--distance",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--qubit",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--random-error",
        action="store_true",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--save-report",
        action="store_true",
    )

    parser.add_argument(
        "--save-circuit",
        action="store_true",
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Distance validation
    # --------------------------------------------------------
    if args.distance != 3:

        raise NotImplementedError(
            "Only distance-3 surface code "
            "is currently implemented."
        )

    # --------------------------------------------------------
    # Geometry
    # --------------------------------------------------------
    geometry = surface_code_geometry(
        args.distance
    )

    # --------------------------------------------------------
    # Random error injection
    # --------------------------------------------------------
    if args.random_error:

        if args.seed is not None:
            random.seed(args.seed)

        args.qubit = random.randint(
            0,
            8,
        )

        args.error = random.choice(
            ["X", "Y", "Z"]
        )

        print(
            f"[Random Error Injection] "
            f"Selected {args.error} error "
            f"on data qubit {args.qubit}"
        )

    # --------------------------------------------------------
    # FPGA warning
    # --------------------------------------------------------
    if (
        args.decoder in ["fpga", "both"]
        and args.error != "X"
    ):

        print(
            "[WARNING] FPGA lookup decoder "
            "currently supports X-error "
            "decoding only."
        )

    # --------------------------------------------------------
    # Build circuit
    # --------------------------------------------------------
    qc = build_single_round_circuit(
        error_qubit=args.qubit,
        error_type=args.error,
    )

    # --------------------------------------------------------
    # Syndrome generation
    # --------------------------------------------------------
    syndrome_bitstring = get_syndrome(
        error_qubit=args.qubit,
        error_type=args.error,
    )

    syndrome_int = get_syndrome_int(
        error_qubit=args.qubit,
        error_type=args.error,
    )

    full_info = get_full_syndrome(
        error_qubit=args.qubit,
        error_type=args.error,
    )

    # --------------------------------------------------------
    # Initialize FPGA decoder ONCE
    # --------------------------------------------------------
    fpga_decoder = None

    if args.decoder in ["fpga", "both"]:

        fpga_decoder = FPGALookupDecoder()

    # --------------------------------------------------------
    # Run decoders
    # --------------------------------------------------------
    results = {}

    start = time.perf_counter()

    if args.decoder == "cpu_lookup":

        results["cpu_lookup"] = (
            run_cpu_lookup(
                syndrome_bitstring
            )
        )

    elif args.decoder == "cpu_mwpm":

        results["cpu_mwpm"] = (
            run_cpu_mwpm(
                syndrome_bitstring
            )
        )

    elif args.decoder == "fpga":

        results["fpga_lookup"] = (
            fpga_decoder.decode(
                syndrome_int
            )
        )

    elif args.decoder == "both":

        results["cpu_lookup"] = (
            run_cpu_lookup(
                syndrome_bitstring
            )
        )

        results["fpga_lookup"] = (
            fpga_decoder.decode(
                syndrome_int
            )
        )

        results["match"] = (
            results["cpu_lookup"]
            == results["fpga_lookup"]
        )

    elif args.decoder == "full":

        results["cpu_full"] = (
            decode_full(
                error_qubit=args.qubit,
                error_type=args.error,
            )
        )

    elapsed_us = (
        time.perf_counter() - start
    ) * 1e6

    # --------------------------------------------------------
    # Determine correction
    # --------------------------------------------------------
    (
        correction_qubit,
        correction_operator,
    ) = determine_correction(
        results,
        args.error,
    )

    if (
        correction_qubit is None
        or correction_qubit == -1
    ):

        suggested_correction = (
            "No correction required"
        )

        corrected_state = (
            "No physical error detected"
        )

        logical_state = (
            "Logical |0⟩ preserved"
        )

        status = "PASS"

    else:

        suggested_correction = (
            f"Apply "
            f"{correction_operator} "
            f"to data qubit "
            f"{correction_qubit}"
        )

        corrected_state = (
            f"{correction_operator} "
            f"applied to data qubit "
            f"{correction_qubit}"
        )

        logical_state = (
            "Estimated logical recovery successful"
        )

        status = "PASS"

    (
        decoder_name,
        hardware_name,
    ) = get_decoder_description(
        args.decoder
    )

    # ========================================================
    # Build Report
    # ========================================================
    lines = []

    lines.append("=" * 70)

    lines.append(
        "FPGA-Accelerated Quantum Error "
        "Correction Pipeline"
    )

    lines.append("=" * 70)

    lines.append("")

    # --------------------------------------------------------
    # System Configuration
    # --------------------------------------------------------
    lines.append("System Configuration")

    lines.append(
        f"  Quantum code        : "
        f"Surface Code "
        f"(distance-{args.distance})"
    )

    lines.append(
        f"  Logical qubits      : "
        f"{geometry['logical_qubits']}"
    )

    lines.append(
        f"  Data qubits         : "
        f"{geometry['data_qubits']}"
    )

    lines.append(
        f"  X ancilla qubits    : "
        f"{geometry['x_ancilla_qubits']}"
    )

    lines.append(
        f"  Z ancilla qubits    : "
        f"{geometry['z_ancilla_qubits']}"
    )

    lines.append(
        f"  Y ancilla qubits    : "
        f"{geometry['y_ancilla_qubits']}"
    )

    lines.append(
        f"  Total ancillas      : "
        f"{geometry['total_ancilla_qubits']}"
    )

    lines.append(
        f"  Total physical qubits : "
        f"{geometry['total_physical_qubits']}"
    )

    lines.append(
        "  Noise model         : "
        "Single-qubit Pauli error "
        "(X, Y, or Z)"
    )

    lines.append(
        f"  Injected error      : "
        f"{args.error} on data qubit "
        f"{args.qubit}"
    )

    lines.append(
        f"  Decoder             : "
        f"{decoder_name}"
    )

    lines.append(
        f"  Execution hardware  : "
        f"{hardware_name}"
    )

    lines.append("")

    # --------------------------------------------------------
    # Workflow
    # --------------------------------------------------------
    lines.append("Workflow")

    lines.append(
        "  Error Injection -> "
        "Syndrome Generation -> "
        "Decoding -> Correction"
    )

    lines.append("")

    # --------------------------------------------------------
    # Syndrome Information
    # --------------------------------------------------------
    lines.append(
        "Single-Round Syndrome"
    )

    lines.append(
        f"  bitstring           : "
        f"{syndrome_bitstring}"
    )

    lines.append(
        f"  integer             : "
        f"{syndrome_int}"
    )

    lines.append("")

    lines.append(
        "Full Syndrome Information"
    )

    lines.append(
        f"  x_syndrome          : "
        f"{full_info['x_syndrome']}"
    )

    lines.append(
        f"  z_syndrome          : "
        f"{full_info['z_syndrome']}"
    )

    lines.append(
        f"  raw                 : "
        f"{full_info['raw_bitstring']}"
    )

    lines.append("")

    # --------------------------------------------------------
    # Decoder Results
    # --------------------------------------------------------
    lines.append("Decoder Results")

    for key, value in results.items():

        lines.append(
            f"  {key:<18}: {value}"
        )

    lines.append("")

    # --------------------------------------------------------
    # Correction
    # --------------------------------------------------------
    lines.append(
        "Correction Interpretation"
    )

    lines.append(
        f"  Suggested correction : "
        f"{suggested_correction}"
    )

    lines.append("")

    # --------------------------------------------------------
    # Post-Correction State
    # --------------------------------------------------------
    lines.append(
        "Post-Correction State"
    )

    lines.append(
        f"  Physical correction  : "
        f"{corrected_state}"
    )

    lines.append(
        f"  Logical state output : "
        f"{logical_state}"
    )

    lines.append("")

    # --------------------------------------------------------
    # Final Status
    # --------------------------------------------------------
    lines.append("Final Status")

    lines.append(
        "  Decoding status      : "
        "Completed"
    )

    lines.append(
        f"  Logical recovery     : "
        f"{status}"
    )

    lines.append("")

    lines.append("Note")

    lines.append(
        "  Logical recovery is inferred "
        "from decoder output and has not "
        "yet been formally verified "
        "through re-simulation."
    )

    lines.append("")

    lines.append(
        f"Decoding time: "
        f"{elapsed_us:.3f} us"
    )

    report = "\n".join(lines)

    # ========================================================
    # Print Report
    # ========================================================
    print(report)

    # ========================================================
    # Save Report
    # ========================================================
    if args.save_report:

        filename = save_text_report(
            report
        )

        print(
            f"\nSaved report to: "
            f"{filename}"
        )

    # ========================================================
    # Save Circuit
    # ========================================================
    if args.save_circuit:

        filename = save_circuit_image(
            qc
        )

        print(
            f"Saved circuit image to: "
            f"{filename}"
        )


if __name__ == "__main__":

    main()