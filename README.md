# FPGA-Accelerated Real-Time Quantum Error Correction Decoder

## 1. Overview

Quantum systems are inherently susceptible to noise and decoherence, which makes error correction essential for reliable computation. In practical Quantum Error Correction (QEC) systems, the classical decoding stage introduces significant latency and can become a critical bottleneck.

This project focuses on the design and implementation of a low-latency, real-time QEC decoder on FPGA. The implementation is evaluated against a CPU-based baseline to analyze improvements in latency and throughput.

---

## 2. Objectives

* Implement a real-time QEC decoder on FPGA
* Support continuous (streaming) syndrome input
* Achieve lower latency than CPU-based decoding
* Maintain full correctness with respect to a reference implementation
* Benchmark performance in terms of latency and throughput

---

## 3. System Architecture

```
Qiskit Noise Model
        ↓
Syndrome Generator (Python)
        ↓
Host Application (C++ / OpenCL)
        ↓
FPGA Decoder Kernel
        ↓
Correction Output
        ↓
(Optional) Feedback to Simulation for Fidelity Evaluation
```

---

## 4. Technology Stack

* Quantum Simulation: Qiskit
* FPGA Toolchain: Xilinx Vitis, XRT
* Host Programming: C++, OpenCL
* Kernel Design: High-Level Synthesis (HLS) in C/C++
* Benchmarking: Python (NumPy, Matplotlib)

---

## 5. Scope

### Included

* Surface code (distance-3) as baseline QEC model
* Greedy decoding algorithm (hardware-friendly)
* FPGA-based decoder implementation
* Streaming syndrome processing
* Performance benchmarking against CPU

### Excluded (Initial Phase)

* Minimum Weight Perfect Matching (MWPM)
* Large-distance surface codes (d > 5)
* Full fault-tolerant circuit implementations

---

## 6. Project Phases

### Phase 1: Problem Definition

* Select QEC code (surface code, distance-3)
* Define syndrome representation and data format
* Implement noise model and syndrome generation

### Phase 2: CPU Baseline

* Implement greedy decoding algorithm
* Validate correctness
* Measure latency and throughput

### Phase 3: FPGA Kernel Development

* Map decoding logic to hardware pipeline
* Optimize loop structures and memory access patterns
* Introduce parallelism where applicable

### Phase 4: Streaming Implementation

* Enable continuous syndrome input
* Implement pipeline-based execution
* Ensure real-time decoding capability

### Phase 5: Benchmarking

* Compare CPU and FPGA implementations
* Measure latency per decode
* Evaluate throughput and correctness

### Phase 6: Extensions (Optional)

* Noise-adaptive decoding strategies
* Approximate matching algorithms
* Scaling to higher code distances

---

## 7. Evaluation Metrics

* Latency per decode (microseconds)
* Throughput (syndromes per second)
* Decoding accuracy
* FPGA resource utilization (LUTs, BRAM, DSPs)

---

## 8. Repository Structure

```
fpga-qec-decoder/
│
├── qiskit_sim/        # Noise models and syndrome generation
├── cpu_decoder/       # Reference CPU implementation
├── fpga/              # FPGA kernel and host code
├── benchmarks/        # Performance evaluation scripts
├── docs/              # Design and architecture documentation
└── README.md
```

---

## 9. Current Status

```
[ ] Repository initialized  
[ ] QEC model defined  
[ ] Syndrome format finalized  
[ ] CPU decoder implemented  
[ ] FPGA kernel implemented  
[ ] Streaming support added  
[ ] Benchmarking completed  
```

---

## 10. Key Challenges

* Mapping irregular decoding logic to efficient hardware pipelines
* Minimizing latency under hardware constraints
* Supporting continuous data streams without bottlenecks
* Preserving correctness while optimizing performance

---

## 11. Goal

The objective is to develop a hardware-accelerated QEC decoder that demonstrates low-latency performance, efficient resource utilization, and practical integration into a quantum-classical hybrid workflow.

---

## 12. Notes

This project emphasizes system-level design, including hardware-aware algorithm development, end-to-end pipeline integration, and performance-driven optimization.
