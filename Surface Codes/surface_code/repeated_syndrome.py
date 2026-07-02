from surface_code.syndrome_generator import get_multi_round_bitstring

def split_rounds(bitstring, rounds, stabilizers_per_round=4):
    """
    Example:

    1111000011110000

    ->
    [
        "1111",
        "0000",
        "1111",
        "0000",
    ]
    """

    round_syndromes = []

def split_rounds(bitstring, rounds, stabilizers_per_round=4):
    bitstring = bitstring[::-1]
    round_syndromes = []
    for r in range(rounds):
        start = r * stabilizers_per_round
        end = start + stabilizers_per_round
        round_syndromes.append(bitstring[start:end])
    return round_syndromes  # make sure this is here
