def inject_error(qc, error):
    """
    Inject multiple Pauli errors into a quantum circuit.

    Parameters
    ----------
    qc : QuantumCircuit

    errors : list
        Example:
        [
            ("X", 1),
            ("Z", 4),
            ("Y", 7),
        ]

    Returns
    -------
    QuantumCircuit
    """
    for error_type, qubit in error:
        if error_type == "X":
            qc.x(qubit)
        elif error_type == "Y":
            qc.y(qubit)
        elif error_type == "Z":
            qc.z(qubit)
        else:
            raise ValueError(f"Invalid error type: {error_type}. Must be 'X', 'Y', or 'Z'.")
    return qc