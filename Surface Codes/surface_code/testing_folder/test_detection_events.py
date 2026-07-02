from surface_code.repeated_syndrome import split_rounds
from surface_code.detection_events import compute_detection_events
from surface_code.syndrome_generator import get_multi_round_bitstring

ROUNDS = 4

for qubit in [0, 4]:
    print(f"\n===== X error on qubit {qubit} =====")

    bitstring = get_multi_round_bitstring(
        rounds=ROUNDS,
        error_qubit=qubit,
        error_type="X",
    )

    rounds = split_rounds(bitstring, ROUNDS)

    print("Per-round syndromes:")
    for i, syndrome in enumerate(rounds):
        print(f"  Round {i}: {syndrome}")

    events = compute_detection_events(rounds)

    print("Detection events:")
    for i, event in enumerate(events):
        print(f"  Round {i}: {event}")