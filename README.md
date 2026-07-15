# FPGA-Accelerated Quantum Error Correction Decoder

## 1. Overview

Quantum systems are inherently susceptible to noise and decoherence, which
makes error correction essential for reliable computation. In practical
Quantum Error Correction (QEC) systems, the classical decoding stage
introduces latency and can become a bottleneck.

This project implements a complete QEC decoding pipeline for the distance-3
surface code: a lookup decoder and an exact MWPM (minimum-weight perfect
matching) decoder, both on CPU and on real FPGA hardware, with correctness
verified statistically and benchmarked honestly against CPU baselines.

> **Note on scope:** all quantum operations are simulated (Qiskit Aer and
> Stim), not run on physical quantum hardware. The FPGA is real. This is a
> batch/offline-style decoder — data moves over PCIe from a host, not
> in-loop on quantum control electronics — so it is not directly comparable
> to real-time streaming decoders used in actual QEC hardware stacks.

---

## 2. Objectives

* Implement a complete decoding pipeline: error injection → syndrome →
  decode → correction → verification
* Provide both a lookup decoder and an exact MWPM decoder, on CPU and FPGA
* Maintain correctness against a statistically verified reference (logical
  error rate curves, tie-aware hardware comparison)
* Benchmark latency and throughput honestly, including cases where the
  FPGA does not win

---

## 3. System Architecture

```text
Qiskit Aer / Stim (simulation only, no physical QPU)
        v
Syndrome generation (Python)
        v
Decoder:
   - CPU lookup     (table derived from geometry)
   - CPU MWPM       (PyMatching; spatial and repeated-round)
   - FPGA lookup    (HLS kernel via PyXRT, real hardware)
   - FPGA MWPM      (bounded bitmask-DP HLS kernel, real hardware)
        v
Correction decision (tie-aware comparison against CPU reference)
        v
Logical recovery check
```

---

## 4. Technology Stack

* Quantum simulation: Qiskit, Qiskit Aer, Stim
* Decoding: PyMatching (CPU reference), custom bounded bitmask-DP matcher (FPGA)
* FPGA toolchain: Xilinx Vitis HLS 2023.2, XRT / PyXRT
* Kernel: High-Level Synthesis (C++), targeting Xilinx Alveo U55C
* Benchmarking / plotting: Python, NumPy, Matplotlib

---

## 5. Scope

### Implemented and Verified

* Distance-3 surface code, corrected checkerboard geometry
* CPU lookup decoder (table derived from geometry, not hand-written)
* CPU MWPM decoder — spatial and repeated-round (spacetime), verified via
  Monte Carlo logical error rate curves
* X+Z decoding together, verified via Stim (noise sweep, both bases,
  monotonic and error-suppressing at low noise)
* FPGA lookup decoder — hardware-verified, benchmarked: ~38x CPU throughput
  on batched syndromes, loses on single-decode latency (PCIe overhead)
* FPGA MWPM decoder — exact bounded bitmask-DP matching (not an
  approximation of blossom; provably optimal for bounded input size),
  hardware-verified 500/500 against the CPU reference, including a case
  that specifically exercises repeated-round decoding: separating a real
  data error from a measurement error across syndrome rounds
* Honest FPGA MWPM benchmark against two CPU baselines: 24.42x faster than
  our own Python pipeline, but PyMatching's peak batched speed is 3.20x
  faster than the FPGA kernel
* A documented, hardware-verified optimization attempt (double-buffered DP
  storage) that did *not* help — 7% slower than the original, with the
  root cause identified (the outer per-syndrome loop was never explicitly
  pipelined, so the fix added cost without unlocking overlap)

### Not Yet Implemented

* Z-error decoding on FPGA (kernel ROM tables are built from the
  Z-stabilizer graph; a second synthesis from the X-stabilizer / Stim
  graph would be needed)
* Simultaneous X-and-Z-on-different-qubits decoding, verified in one
  combined trial (each has been verified independently; the CSS
  structure implies this works, but it has not been run as a specific
  test case)
* Streaming / continuous syndrome input (current design is batch-oriented,
  a deliberate consequence of the PCIe-attached FPGA architecture)
* Code distances d > 3 (geometry is hardcoded)
* The deeper DP-loop optimization (popcount-wavefront restructuring)
  needed to meaningfully close the gap to PyMatching's peak speed

---

## 6. Project Phases

### Phase 1: Problem Definition — done
* Distance-3 surface code, corrected geometry (verified graphlike: every
  single-qubit error flips at most 2 detectors)
* Bit-order convention fixed at the source
* Qiskit-based and Stim-based syndrome generation, both validated

### Phase 2: CPU Decoders — done
* Lookup decoder (derived from geometry)
* MWPM decoder (PyMatching), spatial and repeated-round
* Correctness validated via logical error rate curves (X-only and X+Z)

### Phase 3: FPGA Lookup Kernel — done
* HLS kernel, synthesized, hardware-validated, benchmarked

### Phase 4: FPGA MWPM Kernel — done
* Bounded bitmask-DP matcher, verified exact against PyMatching (2000+
  trials, weight-tie-aware methodology)
* HLS kernel, synthesized, 500/500 hardware validation
* Repeated-round (spacetime) decoding confirmed on real hardware
* Honestly benchmarked against two CPU baselines
* One optimization attempt tried and documented (did not help)

### Phase 5: Benchmarking — done (for X-error decoding, both decoder types)
* Latency and throughput measured for lookup and MWPM, CPU and FPGA
* Results reported without adjustment when the FPGA loses

### Phase 6 (Future): Extensions
* Z-error decoding on FPGA
* Deeper DP optimization (wavefront restructuring)
* Higher code distances
* Streaming input, if a non-PCIe-attached target becomes available

---

## 7. Evaluation Metrics

* Latency per decode (microseconds) — measured separately for single-call
  and batched cases; bitstream load time reported separately from decode
  time, never combined
* Throughput (decodes per second)
* Decoding correctness — statistical verification (Monte Carlo logical
  error rate) plus tie-aware hardware-vs-CPU comparison (exact match,
  legitimate tie, or genuine bug, each counted separately)
* FPGA resource utilization — not yet formally profiled via Vitis Analyzer

---

## 8. Repository Structure

```text
fpga-qec-decoder/
├── surface_code/       # Qiskit + Stim circuits, syndrome generation,
│                       # detection events, spacetime graph
├── cpu_decoder/        # Lookup, MWPM (PyMatching), bounded bitmask-DP
│                       # matcher, correction/logical-error verification
├── fpga_decoder/
│   ├── src/            # HLS kernels: lookup, MWPM (v1 + v2 attempt)
│   ├── tables/          # Generated ROM headers + generator scripts
│   ├── host/             # PyXRT wrappers, hardware validation scripts
│   └── build/              # xclbin outputs (not tracked in git)
├── integration/         # End-to-end pipelines (CPU lookup/MWPM, FPGA
│                        # lookup, FPGA MWPM, Stim X+Z)
├── benchmarks/          # Correctness-gated benchmark scripts
├── results/             # Saved reports, charts, final benchmark records
└── README.md
```

---

## 9. Current Status

```text
[x] Repository initialized
[x] QEC model defined (distance-3 surface code, verified geometry)
[x] Syndrome format and bit-order convention finalized
[x] CPU lookup decoder implemented and verified
[x] CPU MWPM decoder implemented and verified (spatial + repeated-round)
[x] X+Z decoding verified together (Stim track)
[x] FPGA lookup kernel implemented, hardware-verified, benchmarked
[x] FPGA MWPM kernel implemented, hardware-verified, benchmarked
[x] Optimization attempt documented (double-buffering, did not help)
[ ] Z-error decoding on FPGA
[ ] Combined-X-and-Z single-trial verification
[ ] Streaming syndrome input
[ ] Deeper DP-loop optimization (wavefront restructuring)
[ ] FPGA resource utilization formally profiled
```

---

## 10. Key Challenges (Actually Encountered)

* Bit-order mismatches between Qiskit's classical register convention and
  the decoder's expected order — surfaced twice, fixed once at the source
* A broken initial code geometry (one qubit touching all four stabilizers
  of one type), invisible until Monte Carlo testing exposed it
* Boundary matching in MWPM is more permissive than it first appears — a
  single shared boundary node undercounts the true degrees of freedom;
  fixed with per-defect virtual boundary copies
* Distinguishing genuine decoder bugs from legitimate weight ties, which
  requires comparing total matching weight, not just the final answer
* HLS's default scheduling does not overlap outer-loop iterations just
  because a storage hazard is removed — an explicit pipelining directive
  is still required, a lesson learned directly from the v2 optimization
  attempt that didn't help
* A mature, hand-optimized CPU library (PyMatching) is a genuinely hard
  target for a first-pass hardware implementation to beat on raw speed

---

## 11. Goal

Build a hardware-accelerated QEC decoder that demonstrates where FPGA
acceleration genuinely helps (batched lookup decoding) and where a first
implementation does not yet beat mature software (batched MWPM), reporting
both outcomes with the same rigor rather than only the flattering one.

---

## 12. Notes

Quantum data throughout is simulated; the FPGA is real hardware and the
subject of this project. Every benchmark number here has passed a
correctness gate before being reported, and negative results (the FPGA
losing to CPU, an optimization not helping) are documented with the same
care as positive ones.
