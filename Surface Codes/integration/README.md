# FPGA-Accelerated Quantum Error Correction Decoder

A clean, end-to-end framework for simulating the surface code, generating syndromes, decoding errors on CPU and FPGA, and reporting the final logical recovery.

---

## 1. Project Goal

Quantum computers are extremely sensitive to noise.

This project demonstrates the full quantum error correction (QEC) workflow:

1. Inject a physical error (`X`, `Y`, or `Z`) into a surface-code circuit.
2. Measure stabilizers to generate a syndrome.
3. Decode the syndrome using either:
   - CPU Lookup Decoder
   - CPU MWPM Decoder
   - FPGA Lookup Decoder
4. Determine the correction operation.
5. Report whether the logical state is restored.

The main objective is to show how FPGA acceleration can reduce decoding latency.

---

## 2. High-Level Workflow

```text
Logical |0⟩ State
       |
       v
Surface Code Circuit (distance-3)
       |
       v
Inject Physical Error (X, Y, or Z)
       |
       v
Measure Stabilizers
       |
       v
Generate Syndrome Bitstring
       |
       v
Decoder (CPU or FPGA)
       |
       v
Correction Decision
       |
       v
Apply Correction
       |
       v
Logical |0⟩ Restored
```

---

## 3. Surface Code Overview

This project uses the **rotated surface code** with code distance `d = 3`.

### What Does Distance-3 Mean?

- Encodes **1 logical qubit**.
- Corrects **any single physical qubit error**.
- Detects up to two physical errors.

---

## 4. Qubit Layout for Distance-3

For a rotated surface code:

- Data qubits = `d²`
- Total ancilla qubits = `d² - 1`
- Total physical qubits = `2d² - 1`

For `d = 3`:

| Quantity              | Value |
| --------------------- | ----- |
| Logical qubits        | 1     |
| Data qubits           | 9     |
| X ancilla qubits      | 4     |
| Z ancilla qubits      | 4     |
| Y ancilla qubits      | 0     |
| Total ancillas        | 8     |
| Total physical qubits | 17    |

---

## 5. Distance-3 Surface Code Layout

Below is a conceptual layout of the rotated distance-3 surface code used in this project.

```text
D0  D1  D2
D3  D4  D5
D6  D7  D8
```

Where:

- `D0`–`D8` are the 9 data qubits.
- The center qubit `D4` is connected to all four stabilizers.
- Corner qubits connect to one or two stabilizers.
- Edge qubits connect to two stabilizers.

Ancilla qubits:

```text
4 X ancillas  -> detect Z errors
4 Z ancillas  -> detect X errors
```

Total physical qubits:

```text
9 data + 8 ancillas = 17 qubits
```

---

### Example: X Error on Qubit D4

Suppose we inject:

```text
X error on D4
```

Because D4 touches all four Z stabilizers, all four parity checks flip.

Measured syndrome:

```text
1111
```

Lookup decoder mapping:

```text
1111 -> D4
```

Correction:

```text
Apply X to D4
```

Since applying the same Pauli twice gives the identity (`X·X = I`), the physical error is removed and the logical state is restored.

---

### Example: X Error on Qubit D3

Measured syndrome:

```text
0101
```

Lookup decoder:

```text
0101 -> D3
```

Correction:

```text
Apply X to D3
```

---

### Why Each Syndrome Is Unique

In a distance-3 surface code, each single-qubit error produces a unique syndrome pattern.

This is why a simple lookup table is sufficient for correcting any single error.

---

## 6. Why Are Y Ancilla Qubits Zero?

The surface code uses only:

- **X stabilizers** (detect Z errors)
- **Z stabilizers** (detect X errors)

There are no dedicated Y stabilizers.

### Why?

A Y error is equivalent to:

$$
Y = iXZ
$$

So a Y error contains:

- an X component, and
- a Z component.

Therefore:

- Z stabilizers detect the X part.
- X stabilizers detect the Z part.

This means Y errors are detected using existing X and Z ancillas.

**No extra Y ancillas are required.**

---

## 6. Example: Y Error on Qubit 4

```text
Injected error: Y on qubit 4

Y = iXZ

Z stabilizers -> detect X component
X stabilizers -> detect Z component

Both syndrome sets become nonzero.
```

The full decoder combines both syndromes to infer a Y correction.

---

## 7. Decoder Types

### CPU Lookup Decoder

Uses a precomputed table:

```text
syndrome -> correction qubit
```

Fast and simple, but only practical for very small codes.

---

### CPU MWPM Decoder

Uses Minimum-Weight Perfect Matching.

Pros:

- High decoding quality.
- Standard benchmark in QEC.

Cons:

- Complex.
- Hard to map efficiently to FPGA.

---

### FPGA Lookup Decoder

Implements the lookup table as an HLS kernel.

Input:

- Syndrome integer (0–15).

Output:

- Qubit index to correct.

Advantages:

- Extremely low kernel latency.
- Demonstrates hardware acceleration.

---

### Full CPU Decoder

Decodes both:

- X syndrome
- Z syndrome

and combines the results to handle X, Y, and Z errors.

---

## 8. Example Lookup Table (Distance-3)

| Syndrome | Integer | Correction Qubit |
| -------- | ------- | ---------------- |
| 0000     | 0       | -1               |
| 0001     | 1       | 0                |
| 0011     | 3       | 1                |
| 0010     | 2       | 2                |
| 0101     | 5       | 3                |
| 1111     | 15      | 4                |
| 1010     | 10      | 5                |
| 0100     | 4       | 6                |
| 1100     | 12      | 7                |
| 1000     | 8       | 8                |

---

## 9. Repository Structure

```text
qec-fpga-decoder-project/
│
├── surface_code/          # Qiskit circuit generation and syndrome extraction
├── cpu_decoder/           # Lookup, MWPM, and full CPU decoders
├── fpga_decoder/
│   ├── src/               # HLS kernel source
│   ├── host/              # C++ host validation
│   └── build/             # decoder_lookup.xclbin
│
├── integration/           # End-to-end Python pipeline
├── results/               # Saved reports and circuit images
├── benchmarks/            # Performance measurement scripts
└── README.md
```

---

## 10. End-to-End Pipeline Script

Main entry point:

```text
integration/run_decoder_pipeline.py
```

This script:

1. Builds the surface-code circuit.
2. Injects an error.
3. Generates the syndrome.
4. Runs the selected decoder.
5. Interprets the correction.
6. Reports logical recovery.
7. Optionally saves a report and circuit image.

---

## 11. Running the Pipeline

### CPU Lookup Decoder

```bash
python -m integration.run_decoder_pipeline \
    --decoder cpu_lookup \
    --error X \
    --qubit 4
```

### FPGA Lookup Decoder

```bash
python -m integration.run_decoder_pipeline \
    --decoder fpga \
    --error X \
    --qubit 4
```

### Compare CPU and FPGA

```bash
python -m integration.run_decoder_pipeline \
    --decoder both \
    --error X \
    --qubit 4
```

### Full Decoder (handles Y properly)

```bash
python -m integration.run_decoder_pipeline \
    --decoder full \
    --error Y \
    --qubit 4
```

### Random Error Injection

```bash
python -m integration.run_decoder_pipeline \
    --decoder both \
    --random-error
```

### Save Report and Circuit Image

```bash
python -m integration.run_decoder_pipeline \
    --decoder both \
    --random-error \
    --save-report \
    --save-circuit
```

---

## 12. Example Output

```text
System Configuration
  Quantum code          : Surface Code (distance-3)
  Logical qubits        : 1
  Data qubits           : 9
  X ancilla qubits      : 4
  Z ancilla qubits      : 4
  Y ancilla qubits      : 0
  Total ancillas        : 8
  Total physical qubits : 17
  Injected error        : X on data qubit 4
  Decoder               : FPGA Lookup Decoder
  Execution hardware    : Xilinx FPGA

Single-Round Syndrome
  bitstring             : 1111
  integer               : 15

Decoder Results
  fpga_lookup           : 4

Correction Interpretation
  Suggested correction  : Apply X to data qubit 4

Post-Correction State
  Logical state output  : Logical |0⟩ restored
```

---

## 13. FPGA Kernel Workflow

```text
Syndrome Integer (e.g., 15)
          |
          v
qec_decoder kernel
          |
          v
switch(syndrome)
          |
          v
Correction Qubit (4)
```

The FPGA kernel is implemented in:

```text
fpga_decoder/src/qec_decoder.cpp
```

---

## 14. Python-to-FPGA Execution Flow

```text
Python Integration Script
       |
       v
PyXRT
       |
       v
Load decoder_lookup.xclbin
       |
       v
Launch qec_decoder kernel
       |
       v
Read correction output
```

---

## 15. Why Lookup Decoder First?

Lookup decoding is ideal as a first FPGA implementation because:

- Very simple logic.
- Easy to validate.
- Deterministic behavior.
- Provides a hardware baseline.

Limitation:

- Does not scale to larger code distances.

---

## 16. Key Scientific Takeaway

This project demonstrates the complete quantum error correction cycle:

```text
Physical Error
   -> Syndrome Extraction
   -> Classical Decoding
   -> Correction Decision
   -> Logical Recovery
```

with the classical decoding step accelerated on FPGA.

---

## 17. Technologies Used

- Qiskit
- Qiskit Aer
- Python
- NumPy
- Matplotlib
- PyMatching
- Xilinx Vitis HLS
- XRT / PyXRT
- C++

---

##

