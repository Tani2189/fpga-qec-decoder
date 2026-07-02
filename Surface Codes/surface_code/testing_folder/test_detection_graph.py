from surface_code.repeated_syndrome import split_rounds
from surface_code.detection_events import compute_detection_events
from surface_code.syndrome_generator import get_multi_round_bitstring
from surface_code.detection_graph import build_detection_graph, get_active_subgraph

ROUNDS = 4

bitstring = get_multi_round_bitstring(
    rounds=ROUNDS,
    error_qubit=4,
    error_type="X",
)

print("Raw syndrome:")
print(bitstring)

rounds = split_rounds(bitstring, ROUNDS)

print("\nPer-round syndromes:")
for i, syndrome in enumerate(rounds):
    print(f"  Round {i}: {syndrome}")

events = compute_detection_events(rounds)

print("\nDetection events:")
for i, event in enumerate(events):
    print(f"  Round {i}: {event}")

# Detection graph
nodes, space_edges, time_edges = build_detection_graph(events)

print("\nDetection graph nodes (active events):")
for node in nodes:
    print(f"  stabilizer {node[0]}, round {node[1]}")

active_edges = get_active_subgraph(nodes, space_edges, time_edges)
print(f"\nActive subgraph edges for MWPM: {len(active_edges)}")
for edge in active_edges:
    print(f"  {edge[0]} -- {edge[1]}  weight={edge[2]}")