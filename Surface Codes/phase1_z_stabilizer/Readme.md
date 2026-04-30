# Phase 1: Z Stabilizer Syndrome Extraction (d=3 Surface Code Prototype)

## Overview

This module implements a **deterministic stabilizer measurement pipeline** for a distance-3 (d=3) surface-code-inspired lattice, focusing on **Z stabilizers for X-error detection**.

It forms the first stage of a **quantum-to-classical decoding pipeline**, where quantum measurements are converted into structured syndromes suitable for classical processing (e.g., FPGA-based decoding).

---

## System Configuration

* **Data Qubits:** 9
* **Ancilla Qubits:** 4 (Z stabilizers)
* **Stabilizer Type:** Z stabilizers (parity checks)
* **Simulation:** Qiskit Aer (noiseless)
* **Output:** 4-bit syndrome

---

## Stabilizer Structure

Each Z stabilizer measures parity over a subset of data qubits:

* S0 → [0, 1, 3, 4]
* S1 → [1, 2, 4, 5]
* S2 → [3, 4, 6, 7]
* S3 → [4, 5, 7, 8]

Each stabilizer outputs `1` if an odd number of X errors occur in its support.

---

## Example Output

```
No error:      0000
X error @4:    1111
Z error @4:    0000
```

---

## Full X Error Sweep

```
Qubit 0: 0001
Qubit 1: 0011
Qubit 2: 0010
Qubit 3: 0101
Qubit 4: 1111
Qubit 5: 1010
Qubit 6: 0100
Qubit 7: 1100
Qubit 8: 1000
```

This mapping defines the **syndrome-to-qubit relationship**, forming the basis for decoder design.

---

## FPGA Relevance

The syndrome can be converted to an integer:

```
1111 → 15
0000 → 0
```

Enabling a lookup-based decoding model:

```
syndrome (4-bit) → LUT → correction
```

This representation is directly compatible with FPGA-based implementations.

---

## How to Run

### 1. Navigate to project root

```bash
cd qec-fpga-decoder-project
```

---

### 2. Run the module

```bash
python -m surface_code.phase1_z_stabilizer.run_phase1
```

---

### 3. Expected Output

```
===== Z STABILIZER SYNDROME =====
No error:      0000
X error @4:    1111
Z error @4:    0000

===== FULL X ERROR SWEEP =====
Qubit 0: 0001
...
```

---

## Requirements

Install dependencies:

```bash
pip install qiskit qiskit-aer
```

---

## Key Properties

* Deterministic and reproducible
* Clean stabilizer-to-qubit mapping
* FPGA-friendly output format
* Suitable for LUT-based decoding (baseline)

---

## Limitations

This is **not a full surface code implementation**:

* No logical state encoding (not in stabilizer codespace)
* Only Z stabilizers implemented
* Single-round syndrome extraction
* No temporal correlation (no detection events)
* Not suitable for noisy or multi-error decoding

---

## Purpose

Defines the quantum-to-classical interface:

```
Quantum Circuit → Stabilizer Measurement → 4-bit Syndrome
```

This serves as the input layer for classical decoders such as FPGA-based systems.

---

## Next Phase

Phase 2 will introduce:

* Multi-round syndrome extraction
* Detection events: `d(t) = s(t) XOR s(t-1)`
* Time-correlated error tracking

These are essential for realistic quantum error correction and hardware acceleration.

---

## Project Context

Part of an ongoing effort to develop:

> **FPGA-accelerated Quantum Error Correction (QEC) decoders**

Future work includes:

* Detection event pipelines
* Classical decoding algorithms
* FPGA/HLS implementation

---
