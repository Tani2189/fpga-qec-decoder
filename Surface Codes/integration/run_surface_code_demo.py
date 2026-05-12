# integration/run_surface_code_demo.py

from surface_code.syndrome_generator import (
    get_multi_round_bitstring,
    get_full_syndrome,
)
from surface_code.detection_events import get_detection_events


def stage1_demo():
    """
    Stage 1:
    Repeated Z-stabilizer measurements.
    Detects X errors only.
    """
    print("===== STAGE 1: MULTI-ROUND X-ERROR DETECTION =====")

    raw = get_multi_round_bitstring(
        rounds=4,
        error_qubit=4,
        error_type="X",
    )

    syndromes, events = get_detection_events(raw, rounds=4)

    print("Raw bitstring:", raw)
    print("Syndromes:", syndromes)
    print("Detection events:", events)


def stage2_demo():
    """
    Stage 2:
    Full single-round surface-code measurement.
    Detects X, Z, and Y errors.
    """
    print("\n===== STAGE 2: FULL SURFACE CODE =====")

    for error_type in ["X", "Z", "Y"]:
        result = get_full_syndrome(
            error_qubit=4,
            error_type=error_type,
        )

        print(f"\n{error_type} error on qubit 4")
        print("Raw bitstring :", result["raw_bitstring"])
        print("X syndrome    :", result["x_syndrome"])
        print("Z syndrome    :", result["z_syndrome"])


if __name__ == "__main__":
    stage1_demo()
    stage2_demo()