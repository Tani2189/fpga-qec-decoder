# FPGA-Accelerated Quantum Error Correction Decoder

A complete, working pipeline that simulates a quantum surface code, generates
error syndromes, decodes them on CPU and real FPGA hardware, and checks
whether the logical qubit was recovered.

> **Note:** All quantum operations are simulated (Qiskit Aer / Stim). No
> physical quantum computer is used. The real hardware in this project is
> the FPGA, which accelerates the classical decoding step.

---

## 1. What This Project Does

1. Inject an error (`X`, `Y`, or `Z`) into a simulated surface-code circuit.
2. Measure the stabilizers to get a "syndrome" — a pattern that tells us
   something went wrong, without revealing the error directly.
3. Decode the syndrome using one of three methods:
   - **CPU Lookup** — a simple table lookup
   - **CPU MWPM** — Minimum-Weight Perfect Matching (the standard QEC algorithm)
   - **FPGA Lookup** — the same table, running on real FPGA hardware
4. Work out what correction to apply.
5. Check whether the logical qubit is restored.

---

## 2. Workflow

```text
Simulated logical qubit
        |
        v
Surface code circuit (distance-3)
        |
        v
Inject an error (X, Y, or Z)
        |
        v
Measure stabilizers -> syndrome
        |
        v
Decode (CPU or FPGA)
        |
        v
Apply correction
        |
        v
Check logical recovery
```

---

## 3. The Surface Code, Briefly

This project uses a **distance-3 surface code**, the smallest useful version:

- Encodes **1 logical qubit**.
- Can correct **any single physical error**.
- Some errors are indistinguishable from each other (more on this below) —
  either way, the correction still works.

| Quantity              | Value |
| ---------------------- | ----- |
| Logical qubits          | 1     |
| Data qubits             | 9     |
| Z-stabilizers (ancilla) | 4     |
| X-stabilizers (ancilla) | 4     |
| Total physical qubits   | 17    |

Data qubits are arranged on a 3x3 grid:

```text
D0  D1  D2
D3  D4  D5
D6  D7  D8
```

**Z-stabilizers** (catch X errors):
```text
Z0 = {D0, D3}          Z1 = {D1, D2, D4, D5}
Z2 = {D3, D4, D6, D7}  Z3 = {D5, D8}
```

**X-stabilizers** (catch Z errors):
```text
X0 = {D0, D1, D3, D4}  X1 = {D4, D5, D7, D8}
X2 = {D1, D2}          X3 = {D6, D7}
```

Each qubit belongs to at most two stabilizers of a given type, which is what
makes this a valid, decodable code — no qubit's error is too "spread out" to
pin down.

### Example: X error on D4

D4 belongs to Z1 and Z2, so those two checks fire:

```text
X on D4  ->  syndrome 0110  ->  correct D4
```

### A note on ties

A few pairs of qubits (D1/D2, and D6/D7) produce the *same* syndrome. That's
fine — correcting either one restores the logical state, because they only
differ by a "stabilizer" operation, which doesn't change the encoded qubit.
The lookup decoder just needs a consistent rule for picking one; the MWPM
decoder handles this automatically.

### Why there's no separate Y stabilizer

A Y error is just an X error and a Z error happening on the same qubit at
once (`Y = iXZ`). So:
- Z-stabilizers catch the X part.
- X-stabilizers catch the Z part.

No extra hardware is needed to detect Y errors.

---

## 4. Three Decoders, Three Jobs

| Decoder | Errors it handles | Runs on | Status |
| ------- | ------------------ | ------- | ------ |
| CPU Lookup | X only | CPU | Verified |
| CPU MWPM | X only | CPU | Verified (logical error rate curve) |
| FPGA Lookup | X only | Real FPGA | Verified, matches CPU |
| Stim + MWPM | **X and Z** | CPU | Verified (noise sweep, both bases) |

**Why are the first three X-only?** Decoding a Z error requires the qubits
to start in a specific prepared quantum state (not just plain |0⟩). The
Qiskit-based circuits in this project skip that preparation step, so their
Z-stabilizer readings aren't meaningful yet. The Stim-based pipeline solves
this properly and handles both X and Z.

Think of it as two tracks:
- **Qiskit + CPU/FPGA** — the original, hand-built pipeline. X-only, but
  it's the one wired up to real FPGA hardware.
- **Stim + MWPM** — the correctness reference. Handles X and Z properly,
  currently CPU-only.

---

## 5. Repository Structure

```text
fpga-qec-decoder/
├── surface_code/         # Circuit generation and syndrome extraction
│   └── stim_circuits.py  # Stim-based circuits (X+Z, correct state prep)
├── cpu_decoder/          # Lookup, MWPM, and combined decoders
├── fpga_decoder/
│   ├── src/               # HLS kernel source (lookup_fpga.cpp)
│   ├── host/               # C++ host-side test code
│   └── build/               # decoder_lookup.xclbin (built on your machine)
├── integration/
│   ├── common.py                 # Shared reporting code
│   ├── run_x_cpu_pipeline.py     # CPU decoders, X errors only
│   ├── run_fpga_pipeline.py      # FPGA decoder, X errors only
│   └── run_full_xz_pipeline.py   # Stim + MWPM, X and Z errors
├── benchmarks/            # CPU vs FPGA speed comparison
├── results/               # Saved reports, charts, and circuit images
└── README.md
```

---

## 6. Running It

### CPU, MWPM decoder (the most reliable path)
```bash
python -m integration.run_x_cpu_pipeline --decoder cpu_mwpm --error X --qubit 4
```

### CPU, lookup decoder
```bash
python -m integration.run_x_cpu_pipeline --decoder cpu_lookup --error X --qubit 4
```

### FPGA decoder (with automatic CPU comparison)
```bash
python -m integration.run_fpga_pipeline --error X --qubit 4
```

### FPGA decoder only, no comparison
```bash
python -m integration.run_fpga_pipeline --error X --qubit 4 --no-compare
```

### Full X and Z decoding (Stim)
```bash
# One noise level, both error types
python -m integration.run_full_xz_pipeline --noise 0.01 --shots 20000

# Just Z errors
python -m integration.run_full_xz_pipeline --basis X --noise 0.01

# Full verification sweep, saves a chart
python -m integration.run_full_xz_pipeline --sweep --save-plot
```

---

## 7. Example Output

**CPU MWPM:**
```text
Single-Round Syndrome
  bitstring             : 0110
  integer               : 6

Decoder Results
  cpu_mwpm               : [4]

Correction Interpretation
  Suggested correction  : Apply X to data qubit 4
```

**Stim X+Z, noise=0.01, 20,000 shots:**
```text
Basis Z (X errors)
  Logical error rate   : 0.0759

Basis X (Z errors)
  Logical error rate   : 0.0875
```
Both rates track closely, which is expected — the code is roughly symmetric
between X and Z.

---

## 8. How Well Does It Actually Work?

Rather than just claim the decoders work, they've been tested statistically:

- **X-error decoder (CPU/FPGA path):** at a physical error rate of 1%, the
  logical error rate came out to 0.3% — well below the input error rate,
  which is exactly what a working distance-3 code should do.
- **X+Z decoder (Stim path):** logical error rate rises smoothly as noise
  increases, and drops sharply at low noise (0.09% at 0.1% noise), in both
  the X and Z basis. Both curves are provided as saved charts.

---

## 9. FPGA vs CPU: What the Benchmarks Actually Show

Two different, both true, results:

**Single decode (one syndrome at a time):** the CPU wins by a large margin.
Sending one 4-bit number to the FPGA and back costs more time than the
lookup itself takes.

**Batch decode (many syndromes at once):** the FPGA wins by roughly **38x**
in throughput, because the transfer cost is spread across the whole batch.

**The takeaway:** an FPGA only pays off when there's enough work per data
transfer. For a single, tiny lookup, keeping it on the CPU is faster. For
streaming many syndromes, the FPGA pulls ahead.

Charts for both cases are saved under `results/benchmarks/`. Run them
yourself with:
```bash
python -m benchmarks.benchmark_lookup
```

---

## 10. Current Limitations

- Only distance-3 is implemented; the geometry is currently hardcoded.
- The Qiskit/CPU/FPGA pipeline only decodes X errors (see Section 4 for why).
- "Logical recovery" in the CPU/FPGA pipeline reports is inferred from the
  decoder's output, not independently re-verified by re-simulating the
  corrected state.
- The FPGA currently accelerates the lookup decoder only — MWPM
  (the more powerful algorithm) still runs on CPU. FPGA acceleration of
  MWPM is the next major piece of work.
- The lookup table exists in three places (Python, the FPGA source code,
  and the compiled bitstream). If you change the code's geometry, all
  three need to be regenerated and kept in sync.

---

## 11. Technologies Used

Qiskit, Qiskit Aer, Stim, PyMatching, NumPy, Matplotlib, Xilinx Vitis HLS,
XRT / PyXRT, C++.
