# # surface_code/test_syndrome_generator.py

# from surface_code.syndrome_generator import (
#     get_syndrome,
#     get_syndrome_int,
#     get_multi_round_bitstring,
#     get_full_syndrome,
# )


# def run_stage1_tests():
#     """
#     Stage 1 tests:
#     Z stabilizers only.
#     Detect X and Y errors.
#     """
#     print("===== STAGE 1: SINGLE ROUND TESTS =====")

#     # --------------------------------------------------
#     # No error
#     # --------------------------------------------------
#     print("No error:")
#     print(get_syndrome())  # Expected: 0000

#     # --------------------------------------------------
#     # X error test
#     # --------------------------------------------------
#     print("\nX error on qubit 4:")
#     print(get_syndrome(4, "X"))  # Expected: 1111

#     print("\nX error on qubit 4 (int):")
#     print(get_syndrome_int(4, "X"))  # Expected: 15

#     # --------------------------------------------------
#     # Z error test
#     # --------------------------------------------------
#     print("\nZ error on qubit 4:")
#     print(get_syndrome(4, "Z"))  # Expected: 0000

#     print("\nZ error on qubit 4 (int):")
#     print(get_syndrome_int(4, "Z"))  # Expected: 0

#     # --------------------------------------------------
#     # Y error test
#     # --------------------------------------------------
#     print("\nY error on qubit 4:")
#     print(get_syndrome(4, "Y"))  # Expected: same as X error -> 1111

#     # --------------------------------------------------
#     # Full X error sweep
#     # --------------------------------------------------
#     print("\n===== FULL X ERROR SWEEP =====")
#     for q in range(9):
#         print(f"Qubit {q}: {get_syndrome(q, 'X')}")

#     # --------------------------------------------------
#     # Full Z error sweep
#     # --------------------------------------------------
#     print("\n===== FULL Z ERROR SWEEP =====")
#     for q in range(9):
#         print(f"Qubit {q}: {get_syndrome(q, 'Z')}")

#     # --------------------------------------------------
#     # Full Y error sweep
#     # --------------------------------------------------
#     print("\n===== FULL Y ERROR SWEEP =====")
#     for q in range(9):
#         print(f"Qubit {q}: {get_syndrome(q, 'Y')}")

#     # ==================================================
#     # Multi-round tests
#     # ==================================================
#     print("\n===== MULTI ROUND TEST: X ERROR @4 =====")
#     bitstring_x = get_multi_round_bitstring(
#         rounds=4,
#         error_qubit=4,
#         error_type="X",
#     )
#     print("Raw bitstring:")
#     print(bitstring_x)

#     print("\n===== MULTI ROUND TEST: Z ERROR @4 =====")
#     bitstring_z = get_multi_round_bitstring(
#         rounds=4,
#         error_qubit=4,
#         error_type="Z",
#     )
#     print("Raw bitstring:")
#     print(bitstring_z)

#     print("\n===== MULTI ROUND TEST: Y ERROR @4 =====")
#     bitstring_y = get_multi_round_bitstring(
#         rounds=4,
#         error_qubit=4,
#         error_type="Y",
#     )
#     print("Raw bitstring:")
#     print(bitstring_y)


# def run_stage2_tests():
#     print("\n\n===== STAGE 2: FULL SURFACE CODE TESTS =====")

#     # Baseline (no error)
#     print("\nNo error:")
#     baseline = get_full_syndrome()
#     print(baseline)

#     baseline_x = baseline["x_syndrome"]
#     baseline_z = baseline["z_syndrome"]

#     # X error
#     print("\nX error on qubit 4:")
#     result_x = get_full_syndrome(4, "X")
#     print(result_x)

#     assert result_x["x_syndrome"] != baseline_x

#     # Z error
#     print("\nZ error on qubit 4:")
#     result_z = get_full_syndrome(4, "Z")
#     print(result_z)

#     assert result_z["z_syndrome"] != baseline_z

#     # Y error
#     print("\nY error on qubit 4:")
#     result_y = get_full_syndrome(4, "Y")
#     print(result_y)

#     assert result_y["x_syndrome"] != baseline_x
#     assert result_y["z_syndrome"] != baseline_z

#     print("\nStage 2 tests passed.")


# if __name__ == "__main__":
#     run_stage1_tests()
#     run_stage2_tests()

#     print("\nAll syndrome generator tests passed successfully.")

from surface_code.repeated_syndrome import split_rounds
from surface_code.detection_events import compute_detection_events
from surface_code.syndrome_generator import (
    get_multi_round_bitstring,
    inject_measurement_errors,
)

ROUNDS = 4

bitstring = get_multi_round_bitstring(rounds=ROUNDS, error_qubit=4, error_type="X")
rounds = split_rounds(bitstring, ROUNDS)

print("Per-round syndromes (clean):")
for i, s in enumerate(rounds):
    print(f"  Round {i}: {s}")
print("Detection events (clean):")
for i, e in enumerate(compute_detection_events(rounds)):
    print(f"  Round {i}: {e}")

# Inject a measurement error at stabilizer S0, measurement round 2
noisy = inject_measurement_errors(rounds, flips=[(0, 2)])

print("\nPer-round syndromes (meas. error at S0, round 2):")
for i, s in enumerate(noisy):
    print(f"  Round {i}: {s}")
print("Detection events (noisy):")
for i, e in enumerate(compute_detection_events(noisy)):
    print(f"  Round {i}: {e}")