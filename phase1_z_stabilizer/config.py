# surface_code/config.py

NUM_DATA = 9
NUM_ANCILLA_Z = 4

# Z stabilizers (detect X errors)
Z_STABILIZERS = [
    [0, 1, 3, 4],
    [1, 2, 4, 5],
    [3, 4, 6, 7],
    [4, 5, 7, 8]
]