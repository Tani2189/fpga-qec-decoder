from surface_code.phase1_z_stabilizer.syndrome_generator import get_syndrome

# Run directly
if __name__ == "__main__":
    print("===== Z STABILIZER SYNDROME =====")

    print("No error:     ", get_syndrome())
    print("X error @4:   ", get_syndrome(4, 'X'))
    print("Z error @4:   ", get_syndrome(4, 'Z'))

    print("\n===== FULL X ERROR SWEEP =====")

    for q in range(9):
        print(f"Qubit {q}: {get_syndrome(q, 'X')}")