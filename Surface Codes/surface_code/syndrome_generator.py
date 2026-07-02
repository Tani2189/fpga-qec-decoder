import random

from qiskit_aer import AerSimulator
from .circuit_builder import (
    build_single_round_circuit,
    build_multi_round_circuit,
    build_full_single_round_circuit,
)

# Reuse one simulator instance
sim = AerSimulator()


# =========================================================
# Core Execution Helper
# =========================================================
def run_circuit(qc, shots=1):
    """
    Execute a circuit and return the measured bitstring.

    Returns
    -------
    str
        Raw Qiskit bitstring.
    """
    result = sim.run(qc, shots=shots).result()
    counts = result.get_counts()
    return list(counts.keys())[0]


# =========================================================
# Stage 1: Single-Round Z-Stabilizer Syndrome
# =========================================================
def get_syndrome(error_qubit=None, error_type=None, errors=None):
    """
    Generate a single-round syndrome from Z stabilizers only.

    Detects X and Y errors.

    Example:
        get_syndrome(4, "X") -> "1111"
    """
    qc = build_single_round_circuit(
        error_qubit=error_qubit,
        error_type=error_type,
        errors=errors,
    )
    return run_circuit(qc)[::-1]


def get_syndrome_int(
    error_qubit=None,
    error_type=None,
    errors=None,
):
    return int(
        get_syndrome(
            error_qubit=error_qubit,
            error_type=error_type,
            errors=errors,
        ),
        2,
    )


# =========================================================
# Stage 1: Multi-Round Z-Stabilizer Syndrome
# =========================================================
def get_multi_round_bitstring(
    rounds=4,
    error_qubit=None,
    error_type=None,
    error_round=None,
):
    """
    Generate the full raw bitstring from repeated Z-stabilizer
    measurements.

    Example:
        "1111111100000000"
    """
    qc = build_multi_round_circuit(
        rounds=rounds,
        error_qubit=error_qubit,
        error_type=error_type,
        error_round=error_round,
    )
    return run_circuit(qc)


def get_multi_round_circuit(
    rounds=4,
    error_qubit=None,
    error_type=None,
    error_round=None,
):
    """
    Return the multi-round circuit itself.
    """
    return build_multi_round_circuit(
        rounds=rounds,
        error_qubit=error_qubit,
        error_type=error_type,
        error_round=error_round,
    )


# =========================================================
# Stage 2: Full Single-Round Syndrome
# =========================================================
def get_full_syndrome(error_qubit=None, error_type=None, errors=None):
    """
    Measure both stabilizer families.

    Returns
    -------
    dict
        {
            "x_syndrome": str,  # from Z stabilizers (detect X errors)
            "z_syndrome": str,  # from X stabilizers (detect Z errors)
            "raw_bitstring": str
        }

    Expected examples
    -----------------
    X error on qubit 4:
        {
            "x_syndrome": "1111",
            "z_syndrome": "0000"
        }

    Z error on qubit 4:
        {
            "x_syndrome": "0000",
            "z_syndrome": "1111"
        }

    Y error on qubit 4:
        {
            "x_syndrome": "1111",
            "z_syndrome": "1111"
        }
    """
    qc = build_full_single_round_circuit(
        error_qubit=error_qubit,
        error_type=error_type,
        errors=errors,
    )

    raw = run_circuit(qc)

    # Qiskit returns multiple classical registers separated by spaces.
    # Because the circuit was created as:
    # QuantumCircuit(..., c_z, c_x)
    # the returned format is:
    #   "<c_x_bits> <c_z_bits>"
    #
    # Example:
    #   "0000 1111"
    #   c_x = 0000
    #   c_z = 1111
    #
    # Since:
    #   x_syndrome comes from c_z
    #   z_syndrome comes from c_x

    parts = raw.split()

    if len(parts) != 2:
        raise ValueError(
            f"Expected two classical registers in bitstring, got: {raw}"
        )

    c_x_bits, c_z_bits = parts

    return {
        "x_syndrome": c_z_bits,
        "z_syndrome": c_x_bits,
        "raw_bitstring": raw,
    }


# =========================================================
# Measurement (readout) error injection - phenomenological
# =========================================================
def inject_measurement_errors(round_syndromes, p=0.0, flips=None):
    """
    Apply measurement/readout errors to per-round syndromes.

    A measurement error flips a stabilizer's readout bit in ONE round
    only - the next round reads correctly again. This is the
    phenomenological noise model that time-like edges are built to match.

    Parameters
    ----------
    round_syndromes : list[str]
        Per-round syndromes, e.g. ["0000", "0110", "0110", "0110"]
    p : float
        Probability each stabilizer bit is independently flipped, per round.
    flips : list[tuple[int, int]]
        Deterministic (stabilizer_index, round_index) flips - use this for
        testing so you know exactly where the error is.

    Returns
    -------
    list[str]
        New per-round syndromes with the flips applied.
    """
    grid = [list(r) for r in round_syndromes]
    n_rounds = len(grid)
    n_stab = len(grid[0]) if grid else 0

    def flip(s, r):
        grid[r][s] = "1" if grid[r][s] == "0" else "0"

    if flips:
        for (s, r) in flips:
            flip(s, r)

    if p > 0:
        for r in range(n_rounds):
            for s in range(n_stab):
                if random.random() < p:
                    flip(s, r)

    return ["".join(row) for row in grid]