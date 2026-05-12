CODE_DISTANCE = 3
NUM_DATA = 9

# Z stabilizers (detect X errors)
Z_STABILIZERS = [
    [0, 1, 3, 4],
    [1, 2, 4, 5],
    [3, 4, 6, 7],
    [4, 5, 7, 8],
]

# For this simplified d=3 demo, X stabilizers use the same geometry.
X_STABILIZERS = [
    [0, 1, 3, 4],
    [1, 2, 4, 5],
    [3, 4, 6, 7],
    [4, 5, 7, 8],
]

NUM_ANCILLA_Z = len(Z_STABILIZERS)
NUM_ANCILLA_X = len(X_STABILIZERS)