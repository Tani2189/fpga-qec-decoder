# surface_code/testing_folder/test_stim_circuits.py

from surface_code.stim_circuits import (
    make_memory_circuit, sample_detection_events, build_matching,
)

print("===== Noiseless sanity check (both bases) =====")
for basis in ("Z", "X"):
    circuit = make_memory_circuit(basis=basis, distance=3, rounds=4, noise=0.0)
    events, obs = sample_detection_events(circuit, shots=2000, seed=42)

    print(f"\nBasis {basis}:")
    print(f"  detectors fired (should be 0): {events.sum()}")
    print(f"  observable flips (should be 0): {obs.sum()}")
    assert events.sum() == 0, f"Noiseless {basis}-basis circuit has spurious detections!"
    assert obs.sum() == 0, f"Noiseless {basis}-basis circuit has spurious logical flips!"

print("\nPASS: noiseless state prep is deterministic in both bases.\n")

print("===== Decoding under noise =====")
for basis in ("Z", "X"):
    circuit = make_memory_circuit(basis=basis, distance=3, rounds=4, noise=0.01)
    matching = build_matching(circuit)
    events, obs = sample_detection_events(circuit, shots=5000, seed=1)

    predictions = matching.decode_batch(events)
    logical_error_rate = (predictions != obs).any(axis=1).mean()

    print(f"Basis {basis}: logical error rate = {logical_error_rate:.4f}")