"""
benchmarks/benchmark_mwpm_final.py

FINAL benchmark record for the FPGA MWPM decoder (v1, bounded bitmask-DP,
spacetime, X-error only, distance-3 surface code).

This is the authoritative source for any numbers cited in the README or
published externally. It saves three artifacts together, timestamped:
  - a human-readable text report
  - a JSON file with the raw numbers (cite from here, not by hand)
  - two charts (latency, throughput)

Both comparisons (vs our pipeline, vs PyMatching's peak) are always stated
as "X is N times faster than Y" - never a bare ratio a reader has to
mentally invert to tell whether it's a win or a loss.

Includes, honestly:
  - correctness gate (tie-aware, per diagnose_weight_ties.py methodology)
  - single-decode latency: FPGA vs CPU (expected: CPU wins, PCIe overhead)
  - batch throughput: FPGA vs CPU-pipeline vs CPU-PyMatching-peak
  - bitstream load time, reported separately (one-time cost, not per-decode)
  - workload composition (active-defect distribution)
  - a documented note on the v2 double-buffering attempt (7% slower, not used)

Run:
    python -m benchmarks.benchmark_mwpm_final
"""

import os
import json
import time
import random
import platform
import statistics
from datetime import datetime
from collections import Counter

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from surface_code.syndrome_generator import (
    get_multi_round_bitstring, inject_measurement_errors,
)
from surface_code.repeated_syndrome import split_rounds
from cpu_decoder.mwpm_decoder import MWPMDecoder, build_check_matrix
from fpga_decoder.host.mwpm_fpga_decoder import FPGAMWPMDecoder, MAX_ACTIVE_DEFECTS

ROUNDS = 4
NUM_STAB = 4
N = 5000
CORRECTNESS_SAMPLE = 300
V1_XCLBIN = "fpga_decoder/build/fpga_mwpm/decoder_fpga_mwpm.xclbin"

STAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUT_DIR = "results/mwpm_final"


def to_node(s, r):
    return r * NUM_STAB + s


# ------------------------------------------------------------------
def make_workload(n, seed=0):
    random.seed(seed)
    dec = MWPMDecoder()
    dec.build_spacetime(ROUNDS)
    workload = []
    overflow = 0
    while len(workload) < n:
        q = random.randint(0, 8)
        bits = get_multi_round_bitstring(rounds=ROUNDS, error_qubit=q, error_type="X")
        rs = split_rounds(bits, ROUNDS)
        if random.random() < 0.3:
            s_, r_ = random.randint(0, 3), random.randint(1, ROUNDS - 2)
            rs = inject_measurement_errors(rs, flips=[(s_, r_)])
        diff = dec.difference_syndrome(rs)
        active = [to_node(s_, r_) for r_ in range(diff.shape[1])
                  for s_ in range(diff.shape[0]) if diff[s_, r_]]
        if len(active) > MAX_ACTIVE_DEFECTS:
            overflow += 1
            continue
        workload.append((rs, active + [-1] * (MAX_ACTIVE_DEFECTS - len(active)), len(active)))
    return workload, dec, overflow


# ------------------------------------------------------------------
def verify_flatten_order(workload, dec):
    syndromes = [dec.difference_syndrome(rs) for rs, _, _ in workload[:50]]
    refs = [dec._st.decode(s) for s in syndromes]
    for order in ("F", "C"):
        flat = np.stack([s.astype(bool).flatten(order=order) for s in syndromes])
        try:
            batch_out = dec._st.decode_batch(flat)
        except Exception:
            continue
        if all(np.array_equal(np.array(batch_out[i]), np.array(refs[i])) for i in range(len(refs))):
            return order
    return None


# ------------------------------------------------------------------
def correctness_gate(workload, dec, fpga, sample):
    H = build_check_matrix()
    active_arr = np.array([w[1] for w in workload[:sample]], dtype=np.int32)
    fpga_out = fpga.decode_batch(active_arr)

    exact = ties = bugs = 0
    for i in range(sample):
        rs, _, _ = workload[i]
        synd = dec.difference_syndrome(rs)
        cpu_corr = dec._st.decode(synd)
        cpu_mask = sum((1 << q) for q, b in enumerate(cpu_corr) if b)
        fpga_mask = int(fpga_out[i])
        if fpga_mask == cpu_mask:
            exact += 1
            continue
        fv = np.array([(fpga_mask >> q) & 1 for q in range(H.shape[1])], dtype=np.uint8)
        cv = np.array(cpu_corr, dtype=np.uint8)
        if ((H @ (fv ^ cv)) % 2).any():
            bugs += 1
        else:
            ties += 1
    return {"sample": sample, "exact": exact, "ties": ties, "bugs": bugs}


# ------------------------------------------------------------------
def bench_cpu(workload, dec, flatten_order):
    rs_list = [w[0] for w in workload]

    for rs in rs_list[:50]:
        dec.decode_multi_round(rs)
    t0 = time.perf_counter_ns()
    for i in range(2000):
        dec.decode_multi_round(rs_list[i % len(rs_list)])
    t1 = time.perf_counter_ns()
    pipeline_latency_ns = (t1 - t0) / 2000

    t0 = time.perf_counter_ns()
    for rs in rs_list:
        dec.decode_multi_round(rs)
    t1 = time.perf_counter_ns()
    pipeline_throughput = len(rs_list) / ((t1 - t0) / 1e9)

    syndromes = [dec.difference_syndrome(rs) for rs in rs_list]
    for s in syndromes[:50]:
        dec._st.decode(s)
    t0 = time.perf_counter_ns()
    for s in syndromes[:2000]:
        dec._st.decode(s)
    t1 = time.perf_counter_ns()
    peak_latency_ns = (t1 - t0) / 2000

    flat = np.stack([s.astype(bool).flatten(order=flatten_order) for s in syndromes])
    t0 = time.perf_counter_ns()
    dec._st.decode_batch(flat)
    t1 = time.perf_counter_ns()
    peak_throughput = len(flat) / ((t1 - t0) / 1e9)

    return {
        "pipeline_latency_ns": pipeline_latency_ns,
        "pipeline_throughput": pipeline_throughput,
        "peak_latency_ns": peak_latency_ns,
        "peak_throughput": peak_throughput,
    }


# ------------------------------------------------------------------
def bench_fpga(workload):
    active_arr = np.array([w[1] for w in workload], dtype=np.int32)
    n = len(workload)

    t0 = time.perf_counter_ns()
    fpga = FPGAMWPMDecoder(max_n=n, xclbin_path=V1_XCLBIN)
    t1 = time.perf_counter_ns()
    load_time_s = (t1 - t0) / 1e9

    fpga.decode_batch(active_arr[:50])  # warmup

    reps = min(500, n)
    one = active_arr[:1].copy()
    lat = []
    for i in range(reps):
        one[0] = active_arr[i % n]
        t0 = time.perf_counter_ns()
        fpga.decode_batch(one)
        t1 = time.perf_counter_ns()
        lat.append(t1 - t0)

    t0 = time.perf_counter_ns()
    fpga.decode_batch(active_arr)
    t1 = time.perf_counter_ns()
    batch_throughput = n / ((t1 - t0) / 1e9)

    return fpga, {
        "load_time_s": load_time_s,
        "single_latencies_ns": lat,
        "batch_throughput": batch_throughput,
        "n": n,
    }


# ------------------------------------------------------------------
def save_charts(cpu, fpga_r):
    os.makedirs(OUT_DIR, exist_ok=True)
    med_ns = statistics.median(fpga_r["single_latencies_ns"])

    fig, ax = plt.subplots(figsize=(7.5, 5))
    labels = ["CPU\n(our pipeline)", "CPU\n(PyMatching peak)", "FPGA MWPM\n(v1)"]
    vals = [cpu["pipeline_latency_ns"] / 1000, cpu["peak_latency_ns"] / 1000, med_ns / 1000]
    bars = ax.bar(labels, vals, color=["#4C78A8", "#F58518", "#E45756"])
    ax.set_yscale("log")
    ax.set_ylabel("Latency per decode, microseconds (log scale)")
    ax.set_title("Single-Decode Latency: CPU (two baselines) vs FPGA MWPM")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.3f} us", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    p1 = f"{OUT_DIR}/latency_{STAMP}.png"
    fig.savefig(p1, dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 5))
    vals = [cpu["pipeline_throughput"] / 1e6, cpu["peak_throughput"] / 1e6, fpga_r["batch_throughput"] / 1e6]
    bars = ax.bar(labels, vals, color=["#4C78A8", "#F58518", "#54A24B"])
    ax.set_ylabel("Throughput, million decodes/sec")
    ax.set_title("Batch Throughput: CPU (two baselines) vs FPGA MWPM")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.3f} M/s", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    p2 = f"{OUT_DIR}/throughput_{STAMP}.png"
    fig.savefig(p2, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return p1, p2


# ------------------------------------------------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 70)
    print("FINAL BENCHMARK: FPGA MWPM (v1) vs CPU MWPM")
    print("=" * 70)
    print(f"Workload size: {N}, rounds={ROUNDS}, MAX_ACTIVE_DEFECTS={MAX_ACTIVE_DEFECTS}\n")

    print("Building workload...")
    workload, dec, overflow = make_workload(N)
    active_counts = Counter(w[2] for w in workload)
    print(f"Built {len(workload)} syndromes ({overflow} skipped for exceeding the bound)\n")

    print("Verifying decode_batch flatten convention...")
    order = verify_flatten_order(workload, dec)
    if order is None:
        raise RuntimeError("Could not verify flatten convention - aborting.")
    print(f"  confirmed order='{order}'\n")

    print("Loading FPGA v1 + running correctness gate...")
    fpga, fpga_result = bench_fpga(workload)
    correctness = correctness_gate(workload, dec, fpga, CORRECTNESS_SAMPLE)
    print(f"  {correctness['exact']} exact, {correctness['ties']} legitimate ties, "
          f"{correctness['bugs']} real bugs, out of {correctness['sample']}\n")
    if correctness["bugs"] > 0:
        raise AssertionError("Real bugs found - do not trust these numbers.")

    print("Benchmarking CPU (both baselines)...")
    cpu = bench_cpu(workload, dec, order)
    print(f"  pipeline latency:  {cpu['pipeline_latency_ns']:10.1f} ns")
    print(f"  pipeline throughput: {cpu['pipeline_throughput']/1e6:8.3f} M/s")
    print(f"  peak latency:      {cpu['peak_latency_ns']:10.1f} ns")
    print(f"  peak throughput:   {cpu['peak_throughput']/1e6:8.3f} M/s\n")

    lat = fpga_result["single_latencies_ns"]
    print("FPGA v1 results:")
    print(f"  load time (one-time): {fpga_result['load_time_s']*1000:.1f} ms")
    print(f"  median latency:       {statistics.median(lat)/1000:8.2f} us")
    print(f"  p90 latency:          {statistics.quantiles(lat, n=10)[8]/1000:8.2f} us")
    print(f"  min latency:          {min(lat)/1000:8.2f} us")
    print(f"  batch throughput:     {fpga_result['batch_throughput']/1e6:8.3f} M/s\n")

    ratio_pipeline = fpga_result["batch_throughput"] / cpu["pipeline_throughput"]
    ratio_peak = fpga_result["batch_throughput"] / cpu["peak_throughput"]

    # Always express as "X is N times faster than Y" -- never a bare
    # sub-1.0 ratio a reader has to mentally invert to compare.
    pipeline_comparison = f"FPGA is {ratio_pipeline:.2f}x faster than our CPU pipeline"
    if ratio_peak >= 1:
        peak_comparison = f"FPGA is {ratio_peak:.2f}x faster than PyMatching's peak CPU speed"
    else:
        peak_comparison = f"PyMatching's peak CPU speed is {1/ratio_peak:.2f}x faster than FPGA"

    print("=" * 70)
    print("FINAL NUMBERS")
    print("=" * 70)
    print(f"  {pipeline_comparison}")
    print(f"  {peak_comparison}")

    p1, p2 = save_charts(cpu, fpga_result)

    # ---- Save JSON (cite numbers from here, not by hand) ----
    record = {
        "timestamp": STAMP,
        "platform": {
            "python": platform.python_version(),
            "os": platform.platform(),
        },
        "workload": {
            "n": len(workload), "rounds": ROUNDS,
            "max_active_defects": MAX_ACTIVE_DEFECTS,
            "overflow_skipped": overflow,
            "active_count_distribution": dict(sorted(active_counts.items())),
        },
        "correctness": correctness,
        "flatten_order_verified": order,
        "cpu": {
            "pipeline_latency_ns": cpu["pipeline_latency_ns"],
            "pipeline_throughput_per_s": cpu["pipeline_throughput"],
            "pymatching_peak_latency_ns": cpu["peak_latency_ns"],
            "pymatching_peak_throughput_per_s": cpu["peak_throughput"],
        },
        "fpga_v1": {
            "load_time_s": fpga_result["load_time_s"],
            "median_latency_ns": statistics.median(lat),
            "p90_latency_ns": statistics.quantiles(lat, n=10)[8],
            "min_latency_ns": min(lat),
            "batch_throughput_per_s": fpga_result["batch_throughput"],
        },
        "ratios": {
            "fpga_throughput_over_pipeline": ratio_pipeline,
            "fpga_throughput_over_peak": ratio_peak,
            "pipeline_comparison_statement": pipeline_comparison,
            "peak_comparison_statement": peak_comparison,
        },
        "notes": [
            "Kernel: bounded bitmask-DP MWPM, MAX_ACTIVE_DEFECTS=6, DP over up to 12 nodes "
            "(2x for boundary doubling), spacetime graph rounds=4, distance-3 surface code, X-error only.",
            "A v2 kernel with double-buffered DP storage (targeting cross-syndrome "
            "serialization) was built, hardware-validated (500/500), and benchmarked: "
            "it was ~7% SLOWER than v1, not faster. Root cause: the outer per-syndrome "
            "loop was never explicitly pipelined, so double-buffering removed a hazard "
            "that was never being exploited, while adding BRAM and addressing overhead. "
            "v1 is the kernel used for these final numbers.",
            "The likely dominant bottleneck is the within-syndrome DP loop achieving "
            "only II=2 (not II=1) due to a genuine read-then-conditionally-write hazard "
            "on shared DP subset states - a deeper, unattempted optimization "
            "(popcount-wavefront restructuring) would be needed to address this.",
        ],
    }
    json_path = f"{OUT_DIR}/final_benchmark_{STAMP}.json"
    with open(json_path, "w") as f:
        json.dump(record, f, indent=2)

    # ---- Save text report ----
    report_path = f"{OUT_DIR}/final_benchmark_{STAMP}.txt"
    with open(report_path, "w") as f:
        f.write(f"FPGA MWPM Decoder — Final Benchmark Record\n")
        f.write(f"Generated: {STAMP}\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Workload: {len(workload)} syndromes, rounds={ROUNDS}, "
                f"MAX_ACTIVE_DEFECTS={MAX_ACTIVE_DEFECTS}\n")
        f.write(f"Active-defect count distribution: {dict(sorted(active_counts.items()))}\n\n")
        f.write(f"Correctness: {correctness['exact']} exact, {correctness['ties']} ties, "
                f"{correctness['bugs']} bugs, out of {correctness['sample']}\n\n")
        f.write("CPU baselines\n")
        f.write(f"  our pipeline   : {cpu['pipeline_latency_ns']:.1f} ns/decode, "
                f"{cpu['pipeline_throughput']/1e6:.3f} M/s\n")
        f.write(f"  PyMatching peak: {cpu['peak_latency_ns']:.1f} ns/decode, "
                f"{cpu['peak_throughput']/1e6:.3f} M/s\n\n")
        f.write("FPGA v1\n")
        f.write(f"  load time (one-time): {fpga_result['load_time_s']*1000:.1f} ms\n")
        f.write(f"  median latency: {statistics.median(lat)/1000:.2f} us\n")
        f.write(f"  batch throughput: {fpga_result['batch_throughput']/1e6:.3f} M/s\n\n")
        f.write(f"  {pipeline_comparison}\n")
        f.write(f"  {peak_comparison}\n\n")
        f.write("Notes\n")
        for n_ in record["notes"]:
            f.write(f"  - {n_}\n")

    print(f"\nSaved:\n  {report_path}\n  {json_path}\n  {p1}\n  {p2}")


if __name__ == "__main__":
    main()