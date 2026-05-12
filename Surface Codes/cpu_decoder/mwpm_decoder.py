from pymatching import Matching

# Detection-event patterns from your verified sweep
SYNDROME_TO_QUBIT = {
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


def build_matching():
    """
    Build a graph where each syndrome is treated as an edge
    from a boundary node to a virtual detection-event node.
    """
    matching = Matching()

    boundary = 0

    for syndrome, qubit in SYNDROME_TO_QUBIT.items():
        node = int(syndrome, 2)

        matching.add_edge(
            boundary,
            node,
            fault_ids={qubit},
            weight=1.0
        )

    return matching


matching = build_matching()


def decode(syndrome):
    """
    Decode a syndrome string and return a binary correction vector.
    """
    if syndrome == "0000":
        return [0] * 9

    qubit = SYNDROME_TO_QUBIT[syndrome]

    correction = [0] * 9
    correction[qubit] = 1

    return correction


if __name__ == "__main__":
    s = "1111"
    print("Syndrome:", s)
    print("Correction:", decode(s))