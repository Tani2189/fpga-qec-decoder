CODE_DISTANCE = 3
NUM_DATA = 9

# Z stabilizers (detect X errors) - checkerboard, weight-2 on boundaries
Z_STABILIZERS = [
    [0, 3],          # left boundary  (weight 2)
    [1, 2, 4, 5],    # bulk           (weight 4)
    [3, 4, 6, 7],    # bulk           (weight 4)
    [5, 8],          # right boundary (weight 2)
]

# X stabilizers (detect Z errors) - complementary checkerboard
X_STABILIZERS = [
    [0, 1, 3, 4],    # bulk           (weight 4)
    [4, 5, 7, 8],    # bulk           (weight 4)
    [1, 2],          # top boundary   (weight 2)
    [6, 7],          # bottom boundary(weight 2)
]

NUM_ANCILLA_Z = len(Z_STABILIZERS)
NUM_ANCILLA_X = len(X_STABILIZERS)