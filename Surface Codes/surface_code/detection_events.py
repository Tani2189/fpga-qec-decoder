from .config import NUM_ANCILLA_Z


def split_syndromes(bitstring, rounds, bits_per_round=NUM_ANCILLA_Z):
    """
    Split a raw Qiskit bitstring into per-round syndromes.
    """
    # Qiskit reverses bit order
    bitstring = bitstring[::-1]

    expected_len = rounds * bits_per_round
    if len(bitstring) != expected_len:
        raise ValueError(
            f"Expected bitstring length {expected_len}, "
            f"got {len(bitstring)}"
        )

    syndromes = []

    for r in range(rounds):
        start = r * bits_per_round
        end = start + bits_per_round
        syndromes.append(bitstring[start:end])

    return syndromes


def compute_detection_events(syndromes):
    """
    Compute detection events by XORing consecutive syndrome rounds.
    """
    if len(syndromes) < 2:
        return []

    bits_per_round = len(syndromes[0])
    events = []

    for t in range(1, len(syndromes)):
        prev = int(syndromes[t - 1], 2)
        curr = int(syndromes[t], 2)

        xor = prev ^ curr
        events.append(format(xor, f"0{bits_per_round}b"))

    return events


def get_detection_events(
    bitstring,
    rounds,
    bits_per_round=NUM_ANCILLA_Z,
):
    """
    Convert raw bitstring directly to:
        syndromes, detection events
    """
    syndromes = split_syndromes(
        bitstring,
        rounds,
        bits_per_round=bits_per_round,
    )

    events = compute_detection_events(syndromes)

    return syndromes, events


def get_detection_events_from_syndromes(syndromes):
    """
    Convenience wrapper when you already have a list of
    per-round syndromes.
    """
    return compute_detection_events(syndromes)