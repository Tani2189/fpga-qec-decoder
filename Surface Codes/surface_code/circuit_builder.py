from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from .config import (
    NUM_DATA,
    NUM_ANCILLA_Z,
    NUM_ANCILLA_X,
    Z_STABILIZERS,
    X_STABILIZERS,
)


# =========================================================
# Error Injection
# =========================================================
def _inject_errors(qc, data, errors=None):
    """
    Inject a single Pauli error on a data qubit.
    """
    if errors is None:
        return

    for error_type, qubit in errors:
        if error_type == "X":
            qc.x(data[qubit])

        elif error_type == "Y":
            qc.y(data[qubit])

        elif error_type == "Z":
            qc.z(data[qubit])
        else:
            raise ValueError(f"Invalid error type: {error_type}. Must be 'X', 'Y', or 'Z'.")
    return qc


# =========================================================
# Z Stabilizer Measurement
# Detects X errors
# =========================================================
def _measure_z_stabilizers(qc, data, anc_z):
    for anc_idx, stabilizer in enumerate(Z_STABILIZERS):
        for data_idx in stabilizer:
            qc.cx(data[data_idx], anc_z[anc_idx])


# =========================================================
# X Stabilizer Measurement
# Detects Z errors
# =========================================================
def _measure_x_stabilizers(qc, data, anc_x):
    """
    Measure X stabilizers.
    X stabilizers detect Z errors.
    """
    for anc_idx, stabilizer in enumerate(X_STABILIZERS):
        # Ensure ancilla starts in |0>
        qc.reset(anc_x[anc_idx])

        # Prepare |+>
        qc.h(anc_x[anc_idx])

        # Entangle with data qubits
        for data_idx in stabilizer:
            qc.cx(anc_x[anc_idx], data[data_idx])

        # Rotate back to Z basis
        qc.h(anc_x[anc_idx])


# =========================================================
# Stage 1: Single-Round Z Stabilizers Only
# =========================================================
def build_single_round_circuit(error_qubit=None, error_type=None, errors=None,):
    """
    Original single-round circuit:
    Measures only Z stabilizers.
    Detects X errors.
    """
    data = QuantumRegister(NUM_DATA, "data")
    anc = QuantumRegister(NUM_ANCILLA_Z, "anc")
    c = ClassicalRegister(NUM_ANCILLA_Z, "c")

    qc = QuantumCircuit(data, anc, c)

    if errors is not None:

        _inject_errors(
            qc,
            data,
            errors,
        )

    elif (
        error_qubit is not None and error_type is not None):

        _inject_errors(
            qc,
            data,
            [
                (
                    error_type,
                    error_qubit,
                )
            ],
        )
    _measure_z_stabilizers(qc, data, anc)

    for i in range(NUM_ANCILLA_Z):
        qc.measure(anc[i], c[i])

    return qc


# =========================================================
# Stage 1: Multi-Round Z Stabilizers Only
# =========================================================
def build_multi_round_circuit(
    rounds=4,
    error_qubit=None,
    error_type=None,
    error_round=None,
):
    """
    Multi-round repeated Z-stabilizer measurement.
    Detects X errors only.
    """
    if error_round is None:
        error_round = rounds // 2

    data = QuantumRegister(NUM_DATA, "data")
    anc = QuantumRegister(NUM_ANCILLA_Z, "anc")
    c = ClassicalRegister(rounds * NUM_ANCILLA_Z, "c")

    qc = QuantumCircuit(data, anc, c)

    for r in range(rounds):

        if r == error_round:
            _inject_errors(qc, data, [(error_type, error_qubit)] if error_qubit is not None else None)

        _measure_z_stabilizers(qc, data, anc)

        for i in range(NUM_ANCILLA_Z):
            qc.measure(anc[i], c[r * NUM_ANCILLA_Z + i])
            qc.reset(anc[i])

    return qc


# =========================================================
# Stage 2: Full Single-Round Surface-Code Circuit
# Measures both Z and X stabilizers
# =========================================================
def build_full_single_round_circuit(error_qubit=None,error_type=None,errors=None,):
    """
    Build a single-round circuit measuring:

    - Z stabilizers -> detect X errors
    - X stabilizers -> detect Z errors

    Returns both syndrome streams.
    """
    # Registers
    data = QuantumRegister(NUM_DATA, "data")

    anc_z = QuantumRegister(NUM_ANCILLA_Z, "anc_z")
    anc_x = QuantumRegister(NUM_ANCILLA_X, "anc_x")

    c_z = ClassicalRegister(NUM_ANCILLA_Z, "c_z")
    c_x = ClassicalRegister(NUM_ANCILLA_X, "c_x")

    qc = QuantumCircuit(data, anc_z, anc_x, c_z, c_x)

    if errors is not None:

        _inject_errors(
            qc,
            data,
            errors,
        )

    elif (
        error_qubit is not None
        and error_type is not None
    ):

        _inject_errors(
            qc,
            data,
            [
                (
                    error_type,
                    error_qubit,
                )
            ],
        )

    # Measure Z stabilizers (detect X errors)
    _measure_z_stabilizers(qc, data, anc_z)

    # Measure X stabilizers (detect Z errors)
    _measure_x_stabilizers(qc, data, anc_x)

    # Measure ancilla registers
    for i in range(NUM_ANCILLA_Z):
        qc.measure(anc_z[i], c_z[i])

    for i in range(NUM_ANCILLA_X):
        qc.measure(anc_x[i], c_x[i])

    return qc