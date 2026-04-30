from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from surface_code.phase1_z_stabilizer.config import *

def build_z_stabilizer_circuit(error_qubit=None, error_type=None):

    # -------------------------------
    # STEP 1: Registers
    # -------------------------------
    data = QuantumRegister(NUM_DATA, 'data')
    anc = QuantumRegister(NUM_ANCILLA_Z, 'anc')
    c = ClassicalRegister(NUM_ANCILLA_Z, 'c')

    qc = QuantumCircuit(data, anc, c)

    # -------------------------------
    # STEP 2: Initialize |000...>
    # -------------------------------
    for i in range(NUM_DATA):
        qc.reset(data[i])

    # -------------------------------
    # STEP 3: Inject error
    # -------------------------------
    if error_qubit is not None:
        if error_type == 'X':
            qc.x(data[error_qubit])
        elif error_type == 'Z':
            qc.z(data[error_qubit])

    # -------------------------------
    # STEP 4: Z stabilizer measurement
    # -------------------------------
    for i, stabilizer in enumerate(Z_STABILIZERS):
        for q in stabilizer:
            qc.cx(data[q], anc[i])

    # -------------------------------
    # STEP 5: Measure ancillas
    # -------------------------------
    for i in range(NUM_ANCILLA_Z):
        qc.measure(anc[i], c[i])

    return qc