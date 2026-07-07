"""
Stim-based circuit generation for the d=3 rotated surface code.

Adopted narrowly, alongside the existing Qiskit-based stack:
- Qiskit path (circuit_builder.py etc.) remains the hand-built X-error
  demonstrator, validated via the logical error rate curve.
- Stim path (this file) is the correctness oracle for X+Z decoding,
  since it prepares the encoded logical state correctly by construction -
  something the Qiskit circuits do NOT do (data qubits start in bare |0>,
  so X-stabilizer measurement is non-deterministic there).

Basis convention:
    basis="Z" -> memory_z: prepares logical |0>, tracks Z observable.
                 Detects X errors (matches your existing Z-stabilizer work).
    basis="X" -> memory_x: prepares logical |+>, tracks X observable.
                 Detects Z errors (the previously-blocked path).
"""

import stim


def make_memory_circuit(basis="Z", distance=3, rounds=4, noise=0.0):
    """
    Generate a rotated-surface-code memory experiment circuit.

    Parameters
    ----------
    basis : str
        "Z" or "X". Which logical memory experiment to run.
    distance : int
        Code distance (odd, >= 3).
    rounds : int
        Number of stabilizer measurement rounds.
    noise : float
        Depolarizing noise strength after Clifford gates (0.0 = noiseless).

    Returns
    -------
    stim.Circuit
    """
    basis = basis.upper()
    if basis not in ("Z", "X"):
        raise ValueError(f"basis must be 'Z' or 'X', got {basis!r}")

    task = f"surface_code:rotated_memory_{basis.lower()}"

    return stim.Circuit.generated(
        task,
        distance=distance,
        rounds=rounds,
        after_clifford_depolarization=noise,
        after_reset_flip_probability=noise,
        before_measure_flip_probability=noise,
        before_round_data_depolarization=noise,
    )


def sample_detection_events(circuit, shots=1000, seed=None):
    """
    Sample detector outcomes and logical observable flips from a circuit.

    Returns
    -------
    detection_events : np.ndarray, shape (shots, num_detectors), bool
    observable_flips : np.ndarray, shape (shots, num_observables), bool
    """
    sampler = circuit.compile_detector_sampler(seed=seed)
    detection_events, observable_flips = sampler.sample(
        shots=shots, separate_observables=True
    )
    return detection_events, observable_flips


def build_matching(circuit):
    """
    Build a PyMatching decoder from a Stim circuit's detector error model.
    Handles X and Z (whichever basis the circuit encodes) with correct
    spacetime edges, derived automatically - no hand-built check matrix.
    """
    import pymatching
    dem = circuit.detector_error_model(decompose_errors=True)
    return pymatching.Matching.from_detector_error_model(dem)