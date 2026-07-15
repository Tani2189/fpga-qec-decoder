"""
benchmarks/benchmark_mwpm.py

Benchmarks the FPGA MWPM decoder (bounded bitmask-DP, spacetime,
X-error only) against TWO CPU baselines:

  1. Our integrated pipeline's CPU path (includes real string-parsing
     overhead - this is what run_x_cpu_pipeline.py actually pays).
  2. PyMatching's own peak batched throughput (decode_batch on
     pre-parsed numeric arrays - isolates the algorithm's true speed
     from our pipeline's overhead).

Both are reported, honestly labeled, so the FPGA comparison can't be
mistaken for "beats PyMatching's true capability" when it's really
"beats our specific pipeline implementation."

Run:
    python -m benchmarks.benchmark_mwpm
"""

import os
import time
import random
import statistics
from datetime import datetime

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


def to_node(stab, round_):
    return round_ * NUM_STAB + stab


def make_workload(n, seed=0):
    random.seed(seed)
    cpu_decoder = MWPMDecoder()
    cpu_decoder.build_spacetime(ROUNDS)

    workload = []
    skipped_overflow = 0
    while len(workload) < n:
        q = random.randint(0, 8)
        bits = get_multi_round_bitstring(rounds=ROUNDS, error_qubit=q, error_type="X")
        rounds = split_rounds(bits, ROUNDS)
        if random.random() < 0.3:
            s = random.randint(0, NUM_STAB - 1)
            r = random.randint(1, ROUNDS - 2)
            rounds = inject_measurement_errors(rounds, flips=[(s, r)])

        diff = cpu_decoder.difference_syndrome(rounds)
        active = [to_node(s, r) for r in range(diff.shape[1])
                  for s in range(diff.shape[0]) if diff[s, r]]

        if len(active) > MAX_ACTIVE_DEFECTS:
            skipped_overflow += 1
            continue

        padded = active + [-1] * (MAX_ACTIVE_DEFECTS - len(active))
        workload.append((rounds, padded))

    if skipped_overflow:
        print(f"(skipped {skipped_overflow} syndromes exceeding "
              f"MAX_ACTIVE_DEFECTS={MAX_ACTIVE_DEFECTS} while building workload)")
    return workload, cpu_decoder


# ------------------------------------------------------------------
# CPU baseline #1: our integrated pipeline (includes string parsing)
# ------------------------------------------------------------------
def bench_cpu_mwpm_pipeline(workload, cpu_decoder, reps_single=2000):
    round_syndromes_list = [w[0] for w in workload]

    for rs in round_syndromes_list[:50]:
        cpu_decoder.decode_multi_round(rs)

    t0 = time.perf_counter_ns()
    for i in range(reps_single):
        cpu_decoder.decode_multi_round(round_syndromes_list[i % len(round_syndromes_list)])
    t1 = time.perf_counter_ns()
    single_latency_ns = (t1 - t0) / reps_single

    t0 = time.perf_counter_ns()
    for rs in round_syndromes_list:
        cpu_decoder.decode_multi_round(rs)
    t1 = time.perf_counter_ns()
    throughput = len(round_syndromes_list) / ((t1 - t0) / 1e9)

    return single_latency_ns, throughput


# ------------------------------------------------------------------
# CPU baseline #2: PyMatching's peak batched throughput
# ------------------------------------------------------------------
def bench_cpu_mwpm_batched(workload, cpu_decoder):
    """
    Pre-parse all syndromes to numeric arrays ONCE (outside timing), then
    time PyMatching's own decode_batch path - the same vectorized path
    used in the Stim benchmark (~1.5us/decode there).

    IMPORTANT: we don't assume the flatten order decode_batch expects.
    We verify it against individual .decode() calls (already trusted)
    on a sample before using it for timing. If neither row-major ('C')
    nor column-major ('F') flattening reproduces .decode()'s own answers,
    we skip this baseline rather than report an unverified number.
    """
    print("Verifying decode_batch flattening convention...")
    syndromes_2d = [cpu_decoder.difference_syndrome(rs) for rs, _ in workload]

    sample_n = min(50, len(syndromes_2d))
    ref_corrections = [cpu_decoder._st.decode(s) for s in syndromes_2d[:sample_n]]

    def try_convention(order):
        flat_sample = np.stack(
            [s.astype(bool).flatten(order=order) for s in syndromes_2d[:sample_n]]
        )
        try:
            batch_out = cpu_decoder._st.decode_batch(flat_sample)
        except Exception as e:
            return None, str(e)
        match = all(
            np.array_equal(np.array(batch_out[i]), np.array(ref_corrections[i]))
            for i in range(sample_n)
        )
        return match, None

    chosen_order = None
    for order in ("C", "F"):
        ok, err = try_convention(order)
        if err:
            print(f"  order='{order}': decode_batch raised: {err}")
            continue
        print(f"  order='{order}': matches per-shot decode()? {ok}")
        if ok:
            chosen_order = order
            break

    if chosen_order is None:
        print("  Could not verify a flattening convention that reproduces "
              "decode()'s own answers - skipping this baseline rather than "
              "report an unverified number.\n")
        return None

    print(f"  Using order='{chosen_order}' (verified against {sample_n} samples).\n")

    flat_all = np.stack(
        [s.astype(bool).flatten(order=chosen_order) for s in syndromes_2d]
    )

    # per-call loop, pre-parsed (isolates PyMatching's per-call overhead,
    # with NO string parsing - a fairer single-decode number than the
    # pipeline baseline above)
    t0 = time.perf_counter_ns()
    for s in syndromes_2d[:2000]:
        cpu_decoder._st.decode(s)
    t1 = time.perf_counter_ns()
    single_latency_ns = (t1 - t0) / 2000

    # true batched throughput - PyMatching's peak speed
    t0 = time.perf_counter_ns()
    cpu_decoder._st.decode_batch(flat_all)
    t1 = time.perf_counter_ns()
    throughput = len(flat_all) / ((t1 - t0) / 1e9)

    return {
        "single_latency_ns": single_latency_ns,
        "throughput": throughput,
        "order": chosen_order,
    }


# ------------------------------------------------------------------
# FPGA MWPM benchmark
# ------------------------------------------------------------------
def bench_fpga_mwpm(workload):
    active_list = [w[1] for w in workload]
    active_arr = np.array(active_list, dtype=np.int32)
    N = len(active_list)

    t0 = time.perf_counter_ns()
    fpga = FPGAMWPMDecoder(max_n=N)
    t1 = time.perf_counter_ns()
    load_time_s = (t1 - t0) / 1e9

    fpga.decode_batch(active_arr[: min(50, N)])

    reps = min(500, N)
    one = active_arr[:1].copy()
    times = []
    for i in range(reps):
        one[0] = active_arr[i % N]
        t0 = time.perf_counter_ns()
        fpga.decode_batch(one)
        t1 = time.perf_counter_ns()
        times.append(t1 - t0)

    t0 = time.perf_counter_ns()
    fpga.decode_batch(active_arr)
    t1 = time.perf_counter_ns()
    batch_time_s = (t1 - t0) / 1e9
    throughput = N / batch_time_s

    return {
        "load_time_s": load_time_s,
        "single_latencies_ns": times,
        "batch_throughput": throughput,
        "batch_time_s": batch_time_s,
        "n": N,
    }


# ------------------------------------------------------------------
# Correctness gate (ties-aware, per diagnose_weight_ties.py logic)
# ------------------------------------------------------------------
def verify_correctness(workload, cpu_decoder, fpga, sample=200):
    H = build_check_matrix()
    sample_n = min(sample, len(workload))
    active_arr = np.array([w[1] for w in workload[:sample_n]], dtype=np.int32)
    fpga_out = fpga.decode_batch(active_arr)

    exact, ties, real_bugs = 0, 0, 0

    for i in range(sample_n):
        rounds, _ = workload[i]
        syndrome = cpu_decoder.difference_syndrome(rounds)
        cpu_correction = cpu_decoder._st.decode(syndrome)
        cpu_mask = 0
        for q, b in enumerate(cpu_correction):
            if b:
                cpu_mask |= (1 << q)

        fpga_mask = int(fpga_out[i])

        if fpga_mask == cpu_mask:
            exact += 1
            continue

        fpga_vec = np.array([(fpga_mask >> q) & 1 for q in range(H.shape[1])], dtype=np.uint8)
        cpu_vec = np.array(cpu_correction, dtype=np.uint8)
        residual_syndrome = (H @ (fpga_vec ^ cpu_vec)) % 2

        if residual_syndrome.any():
            real_bugs += 1
            print(f"  REAL BUG #{i}: fpga=0x{fpga_mask:x} cpu=0x{cpu_mask:x} "
                  f"residual_syndrome={list(residual_syndrome)}")
        else:
            ties += 1

    print(f"Correctness gate: {exact} exact, {ties} legitimate ties, "
          f"{real_bugs} real bugs, out of {sample_n}\n")

    if real_bugs > 0:
        raise AssertionError(f"{real_bugs} real bugs found - do not trust timing results.")


# ------------------------------------------------------------------
# Plots
# ------------------------------------------------------------------
def save_plots(cpu_pipeline_lat_ns, cpu_pipeline_tput, cpu_batched, fpga_result):
    os.makedirs("results/benchmarks", exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    fpga_median_ns = statistics.median(fpga_result["single_latencies_ns"])

    # Throughput: three-way if batched CPU baseline is available
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["CPU\n(our pipeline)", "FPGA MWPM\n(batched)"]
    values = [cpu_pipeline_tput / 1e6, fpga_result["batch_throughput"] / 1e6]
    colors = ["#4C78A8", "#54A24B"]
    if cpu_batched is not None:
        labels.insert(1, "CPU MWPM\n(PyMatching peak)")
        values.insert(1, cpu_batched["throughput"] / 1e6)
        colors.insert(1, "#F58518")

    bars = ax.bar(labels, values, color=colors)
    ax.set_ylabel("Throughput, million decodes/sec")
    ax.set_title("Batch Throughput: CPU (two baselines) vs FPGA MWPM")
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.3f} M/s",
                ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    p1 = f"results/benchmarks/mwpm_throughput_{stamp}.png"
    fig.savefig(p1, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return p1


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    N = 5000
    print("=" * 70)
    print("MWPM Decoder Benchmark: CPU (two baselines) vs FPGA (bounded bitmask-DP)")
    print("=" * 70)
    print(f"Workload: {N} repeated-round syndromes, rounds={ROUNDS}, "
          f"mixed data + measurement errors\n")

    print("Building workload...")
    workload, cpu_decoder = make_workload(N)
    print(f"Built {len(workload)} syndromes.\n")

    print("Loading FPGA bitstream + running correctness gate...")
    fpga = FPGAMWPMDecoder(max_n=N)
    verify_correctness(workload, cpu_decoder, fpga)

    print("Benchmarking CPU MWPM - baseline 1: our integrated pipeline...")
    cpu_pipeline_lat_ns, cpu_pipeline_tput = bench_cpu_mwpm_pipeline(workload, cpu_decoder)
    print(f"  single-decode latency (amortized): {cpu_pipeline_lat_ns:10.1f} ns")
    print(f"  throughput:                        {cpu_pipeline_tput/1e6:10.3f} M decodes/s\n")

    print("Benchmarking CPU MWPM - baseline 2: PyMatching peak (batched)...")
    cpu_batched = bench_cpu_mwpm_batched(workload, cpu_decoder)
    if cpu_batched:
        print(f"  single-decode latency (pre-parsed): {cpu_batched['single_latency_ns']:10.1f} ns")
        print(f"  throughput (decode_batch):          {cpu_batched['throughput']/1e6:10.3f} M decodes/s\n")

    print("Benchmarking FPGA MWPM...")
    fpga_result = bench_fpga_mwpm(workload)
    lat = fpga_result["single_latencies_ns"]
    print(f"  bitstream load time (one-time, NOT per-decode): "
          f"{fpga_result['load_time_s']*1000:.1f} ms")
    print(f"  single-decode median latency: {statistics.median(lat)/1000:10.2f} us")
    print(f"  single-decode p90 latency:    {statistics.quantiles(lat, n=10)[8]/1000:10.2f} us")
    print(f"  batch throughput ({fpga_result['n']} syndromes, 1 round-trip): "
          f"{fpga_result['batch_throughput']/1e6:10.3f} M decodes/s\n")

    print("=" * 70)
    print("Interpretation")
    print("=" * 70)
    ratio_pipeline = fpga_result["batch_throughput"] / cpu_pipeline_tput
    print(f"vs our integrated pipeline: FPGA is {ratio_pipeline:.2f}x "
          f"{'faster' if ratio_pipeline > 1 else 'slower'} "
          f"(CPU {cpu_pipeline_tput/1e6:.3f} vs FPGA {fpga_result['batch_throughput']/1e6:.3f} M/s)")

    if cpu_batched:
        ratio_peak = fpga_result["batch_throughput"] / cpu_batched["throughput"]
        print(f"vs PyMatching's peak batched speed: FPGA is {ratio_peak:.2f}x "
              f"{'faster' if ratio_peak > 1 else 'slower'} "
              f"(CPU {cpu_batched['throughput']/1e6:.3f} vs FPGA {fpga_result['batch_throughput']/1e6:.3f} M/s)")
        print("\nThis second comparison is the fair, defensible one - it isolates")
        print("PyMatching's true algorithmic speed from our pipeline's Python overhead.")
    else:
        print("\nPyMatching peak baseline unavailable (see above) - only the")
        print("integrated-pipeline comparison is reportable this run.")

    p1 = save_plots(cpu_pipeline_lat_ns, cpu_pipeline_tput, cpu_batched, fpga_result)
    print(f"\nSaved: {p1}")


if __name__ == "__main__":
    main()