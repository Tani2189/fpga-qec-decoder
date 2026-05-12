"""
Lookup-table decoder for the d=3 surface code.

This decoder assumes:
- Only single X errors.
- Input is a 4-bit syndrome string.
- Output is the data qubit index to correct.
"""

# syndrome -> data qubit
LOOKUP_TABLE = {
    "0001": 0,
    "0011": 1,
    "0010": 2,
    "0101": 3,
    "1111": 4,
    "1010": 5,
    "0100": 6,
    "1100": 7,
    "1000": 8,
}


def decode(syndrome):
    """
    Decode a 4-bit syndrome.

    Parameters
    ----------
    syndrome : str
        Example: '1111'

    Returns
    -------
    int or None
        Data qubit index to correct.
        None if syndrome is '0000' or unknown.
    """
    if syndrome == "0000":
        return None

    return LOOKUP_TABLE.get(syndrome, None)


def get_correction(syndrome):
    """
    Return a correction dictionary.
    """
    qubit = decode(syndrome)

    if qubit is None:
        return {
            "error_qubit": None,
            "correction": None,
        }

    return {
        "error_qubit": qubit,
        "correction": ("X", qubit),
    }


if __name__ == "__main__":
    test_syndrome = "1111"

    print("Input syndrome:", test_syndrome)
    print("Decoded qubit:", decode(test_syndrome))
    print("Correction:", get_correction(test_syndrome))