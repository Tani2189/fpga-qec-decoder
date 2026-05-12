from surface_code.syndrome_generator import get_full_syndrome

print("Z_SYNDROME_TO_QUBIT = {")

for q in range(9):
    result = get_full_syndrome(q, "Z")
    z_syndrome = result["z_syndrome"]
    print(f'    "{z_syndrome}": {q},')

print("}")
