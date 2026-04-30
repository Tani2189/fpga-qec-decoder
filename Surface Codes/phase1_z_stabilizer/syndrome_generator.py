from qiskit_aer import AerSimulator
from surface_code.phase1_z_stabilizer.surface_code_d3 import build_z_stabilizer_circuit

sim = AerSimulator()

def get_syndrome(error_qubit=None, error_type=None):
    qc = build_z_stabilizer_circuit(error_qubit, error_type)
    result = sim.run(qc, shots=1).result()
    bitstring = list(result.get_counts().keys())[0]
    return bitstring

def get_syndrome_int(error_qubit=None, error_type=None):
    bitstring = get_syndrome(error_qubit, error_type)
    return int(bitstring, 2)

print("X error @4 (int):", get_syndrome_int(4, 'X'))

