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
def _inject_error(qc, data, error_qubit=None, error_type=None):
    """
    Inject a single Pauli error on a data qubit.
    """
    if error_qubit is None:
        return

    if error_type == "X":
        qc.x(data[error_qubit])
    elif error_type == "Z":
        qc.z(data[error_qubit])
    elif error_type == "Y":
        qc.y(data[error_qubit])
    else:
        raise ValueError(f"Unsupported error type: {error_type}")


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
def build_single_round_circuit(error_qubit=None, error_type=None):
    """
    Original single-round circuit:
    Measures only Z stabilizers.
    Detects X errors.
    """
    data = QuantumRegister(NUM_DATA, "data")
    anc = QuantumRegister(NUM_ANCILLA_Z, "anc")
    c = ClassicalRegister(NUM_ANCILLA_Z, "c")

    qc = QuantumCircuit(data, anc, c)

    _inject_error(qc, data, error_qubit, error_type)
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
            _inject_error(qc, data, error_qubit, error_type)

        _measure_z_stabilizers(qc, data, anc)

        for i in range(NUM_ANCILLA_Z):
            qc.measure(anc[i], c[r * NUM_ANCILLA_Z + i])
            qc.reset(anc[i])

    return qc


# =========================================================
# Stage 2: Full Single-Round Surface-Code Circuit
# Measures both Z and X stabilizers
# =========================================================
def build_full_single_round_circuit(
    error_qubit=None,
    error_type=None,
):
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

    # Inject optional X / Y / Z error
    _inject_error(qc, data, error_qubit, error_type)

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