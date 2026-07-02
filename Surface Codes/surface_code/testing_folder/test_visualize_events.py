from surface_code.repeated_syndrome import (
    split_rounds,
)

from surface_code.detection_events import (
    compute_detection_events,
)

from surface_code.syndrome_generator import (
    get_multi_round_bitstring,
)

from surface_code.visualize_events import (
    plot_detection_events,
)


ROUNDS = 4

bitstring = get_multi_round_bitstring(
    rounds=ROUNDS,
    error_qubit=4,
    error_type="X",
)

print("Raw syndrome:")
print(bitstring)

round_syndromes = split_rounds(
    bitstring,
    ROUNDS,
)

events = compute_detection_events(
    round_syndromes
)

print("\nDetection Events")

for i, event in enumerate(events):
    print(
        f"Round {i}: {event}"
    )

plot_detection_events(events)