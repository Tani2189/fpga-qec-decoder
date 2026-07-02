from surface_code.config import Z_STABILIZERS, NUM_DATA

def build_lookup_table(stabilizers=Z_STABILIZERS, num_data=NUM_DATA):
    table = {}
    for q in range(num_data):
        bits = ["0"] * len(stabilizers)
        for s, qubits in enumerate(stabilizers):
            if q in qubits:
                bits[s] = "1"
        table["".join(bits)] = q
    return table

LOOKUP_TABLE = build_lookup_table()

def decode(syndrome):
    if syndrome == "0000":
        return None
    return LOOKUP_TABLE.get(syndrome, None)

def get_correction(syndrome):
    qubit = decode(syndrome)
    if qubit is None:
        return {"error_qubit": None, "correction": None}
    return {"error_qubit": qubit, "correction": ("X", qubit)}