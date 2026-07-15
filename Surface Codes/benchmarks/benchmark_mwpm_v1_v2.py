"""
benchmarks/benchmark_mwpm_v1_v2.py

Compares FPGA MWPM v1 (baseline) vs v2 (double-buffered) against both
CPU baselines (our pipeline, and PyMatching's peak batched speed).

Run:
    python -m benchmarks.benchmark_mwpm_v1_v2
"""
import time, random, statistics
import numpy as np

from surface_code.syndrome_generator import get_multi_round_bitstring, inject_measurement_errors
from surface_code.repeated_syndrome import split_rounds
from cpu_decoder.mwpm_decoder import MWPMDecoder, build_check_matrix
from fpga_decoder.host.mwpm_fpga_decoder import FPGAMWPMDecoder, MAX_ACTIVE_DEFECTS

ROUNDS, NUM_STAB = 4, 4
V1_XCLBIN = "fpga_decoder/build/fpga_mwpm/decoder_fpga_mwpm.xclbin"
V2_XCLBIN = "fpga_decoder/build/fpga_mwpm_v2/decoder_fpga_mwpm_v2.xclbin"


def to_node(s, r): return r * NUM_STAB + s


def make_workload(n, seed=0):
    random.seed(seed)
    dec = MWPMDecoder(); dec.build_spacetime(ROUNDS)
    workload = []
    while len(workload) < n:
        q = random.randint(0, 8)
        bits = get_multi_round_bitstring(rounds=ROUNDS, error_qubit=q, error_type="X")
        rs = split_rounds(bits, ROUNDS)
        if random.random() < 0.3:
            s_, r_ = random.randint(0, 3), random.randint(1, ROUNDS - 2)
            rs = inject_measurement_errors(rs, flips=[(s_, r_)])
        diff = dec.difference_syndrome(rs)
        active = [to_node(s_, r_) for r_ in range(diff.shape[1]) for s_ in range(diff.shape[0]) if diff[s_, r_]]
        if len(active) > MAX_ACTIVE_DEFECTS:
            continue
        workload.append((rs, active + [-1] * (MAX_ACTIVE_DEFECTS - len(active))))
    return workload, dec


def verify(workload, dec, fpga, label, sample=200):
    H = build_check_matrix()
    active_arr = np.array([w[1] for w in workload[:sample]], dtype=np.int32)
    out = fpga.decode_batch(active_arr)
    exact, ties, bugs = 0, 0, 0
    for i in range(sample):
        rs, _ = workload[i]
        synd = dec.difference_syndrome(rs)
        cpu_corr = dec._st.decode(synd)
        cpu_mask = sum((1 << q) for q, b in enumerate(cpu_corr) if b)
        if int(out[i]) == cpu_mask:
            exact += 1; continue
        fv = np.array([(int(out[i]) >> q) & 1 for q in range(H.shape[1])], dtype=np.uint8)
        cv = np.array(cpu_corr, dtype=np.uint8)
        if ((H @ (fv ^ cv)) % 2).any():
            bugs += 1
        else:
            ties += 1
    print(f"[{label}] correctness: {exact} exact, {ties} ties, {bugs} bugs / {sample}")
    if bugs:
        raise AssertionError(f"{label}: {bugs} real bugs - do not trust its numbers")


def bench_fpga(workload, xclbin_path, label):
    active_arr = np.array([w[1] for w in workload], dtype=np.int32)
    N = len(workload)
    fpga = FPGAMWPMDecoder(max_n=N, xclbin_path=xclbin_path)
    verify(workload, cpu_decoder_global, fpga, label)
    fpga.decode_batch(active_arr[:50])  # warmup
    t0 = time.perf_counter_ns()
    fpga.decode_batch(active_arr)
    t1 = time.perf_counter_ns()
    throughput = N / ((t1 - t0) / 1e9)
    print(f"[{label}] batch throughput: {throughput/1e6:.3f} M decodes/s\n")
    return throughput


def bench_cpu(workload, dec):
    rs_list = [w[0] for w in workload]
    t0 = time.perf_counter_ns()
    for rs in rs_list:
        dec.decode_multi_round(rs)
    t1 = time.perf_counter_ns()
    pipeline_tput = len(rs_list) / ((t1 - t0) / 1e9)

    syndromes = [dec.difference_syndrome(rs) for rs in rs_list]
    flat = np.stack([s.astype(bool).flatten(order="F") for s in syndromes])
    t0 = time.perf_counter_ns()
    dec._st.decode_batch(flat)
    t1 = time.perf_counter_ns()
    peak_tput = len(flat) / ((t1 - t0) / 1e9)
    return pipeline_tput, peak_tput


def main():
    global cpu_decoder_global
    N = 5000
    print(f"Building {N}-syndrome workload...\n")
    workload, dec = make_workload(N)
    cpu_decoder_global = dec

    print("=== CPU baselines ===")
    pipeline_tput, peak_tput = bench_cpu(workload, dec)
    print(f"our pipeline:        {pipeline_tput/1e6:.3f} M decodes/s")
    print(f"PyMatching peak:     {peak_tput/1e6:.3f} M decodes/s\n")

    print("=== FPGA v1 (baseline) ===")
    v1_tput = bench_fpga(workload, V1_XCLBIN, "v1")

    print("=== FPGA v2 (double-buffered) ===")
    v2_tput = bench_fpga(workload, V2_XCLBIN, "v2")

    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"CPU (our pipeline):   {pipeline_tput/1e6:8.3f} M/s")
    print(f"CPU (PyMatching peak):{peak_tput/1e6:8.3f} M/s")
    print(f"FPGA v1:              {v1_tput/1e6:8.3f} M/s   ({v1_tput/pipeline_tput:.2f}x pipeline, {v1_tput/peak_tput:.2f}x peak)")
    print(f"FPGA v2:              {v2_tput/1e6:8.3f} M/s   ({v2_tput/pipeline_tput:.2f}x pipeline, {v2_tput/peak_tput:.2f}x peak)")
    print(f"v2 improvement over v1: {v2_tput/v1_tput:.2f}x")


if __name__ == "__main__":
    main()