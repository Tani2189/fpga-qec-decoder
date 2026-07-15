"""
Lookup decoder benchmark: CPU vs FPGA, single-decode latency + batch throughput,
with saved benchmark images.

Honest caveats (read before citing numbers):
- Single 4-bit lookups are trivial work. Expect the FPGA to LOSE on
  single-decode wall-clock latency because every decode pays a PCIe
  round-trip that dwarfs the lookup itself. This is expected and correct.
- The "kernel(host-observed)" number includes XRT dispatch overhead, not
  just raw compute. True kernel latency needs Vitis hardware profiling.
- The CPU decoder is a pure-Python dict lookup. A numpy-vectorized CPU
  lookup would be far faster; this measures the decoder as built.

Run:
    python -m benchmarks.benchmark_lookup
"""

import os
import time
import statistics
from datetime import datetime
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")   # headless-safe: works over SSH / no display
import matplotlib.pyplot as plt

from cpu_decoder.lookup_decoder import decode as cpu_lookup_decode

try:
    import pyxrt
    PYXRT_AVAILABLE = True
except ImportError:
    PYXRT_AVAILABLE = False


# ------------------------------------------------------------------
# Test data
# ------------------------------------------------------------------
def make_syndromes(n, seed=0):
    rng = np.random.default_rng(seed)
    ints = rng.integers(0, 16, size=n, dtype=np.int32)
    strs = [format(int(i), "04b") for i in ints]
    return ints, strs


def cpu_result(s):
    """Normalize CPU output to match FPGA's -1 convention."""
    r = cpu_lookup_decode(s)
    return -1 if r is None else r


# ------------------------------------------------------------------
# Batch-capable FPGA decoder (one PCIe round-trip for N syndromes)
# ------------------------------------------------------------------
class FPGABatchDecoder:
    def __init__(self, max_n):
        repo_root = Path(__file__).resolve().parents[1]
        xclbin_path = repo_root / "fpga_decoder" / "build" / "fpga_lookup_decoder.xclbin"
        if not xclbin_path.exists():
            raise FileNotFoundError(f"xclbin not found: {xclbin_path}")

        self.device = pyxrt.device(0)
        self.xclbin = pyxrt.xclbin(str(xclbin_path))
        self.uuid = self.device.load_xclbin(self.xclbin)
        self.kernel = pyxrt.kernel(self.device, self.uuid, "qec_decoder")

        self.max_n = max_n
        self.in_arr = np.zeros(max_n, dtype=np.int32)
        self.out_arr = np.zeros(max_n, dtype=np.int32)
        self.in_bo = pyxrt.bo(self.device, self.in_arr.nbytes,
                              pyxrt.bo.normal, self.kernel.group_id(0))
        self.out_bo = pyxrt.bo(self.device, self.out_arr.nbytes,
                               pyxrt.bo.normal, self.kernel.group_id(1))
        self.D = pyxrt.xclBOSyncDirection

    def decode_batch(self, ints, timing=False):
        n = len(ints)
        self.in_arr[:n] = ints
        nbytes = int(self.in_arr[:n].nbytes)

        t0 = time.perf_counter_ns()
        self.in_bo.write(self.in_arr[:n], 0)
        self.in_bo.sync(self.D.XCL_BO_SYNC_BO_TO_DEVICE, nbytes, 0)
        t1 = time.perf_counter_ns()
        run = self.kernel(self.in_bo, self.out_bo, np.int32(n))
        run.wait()
        t2 = time.perf_counter_ns()
        self.out_bo.sync(self.D.XCL_BO_SYNC_BO_FROM_DEVICE, nbytes, 0)
        out = np.frombuffer(self.out_bo.read(nbytes, 0), dtype=np.int32).copy()
        t3 = time.perf_counter_ns()

        if timing:
            return out, {"xfer_in": t1 - t0, "kernel": t2 - t1, "xfer_out": t3 - t2}
        return out


# ------------------------------------------------------------------
# Correctness gate — must pass before any timing
# ------------------------------------------------------------------
def verify(ints, strs, fpga):
    cpu = np.array([cpu_result(s) for s in strs], dtype=np.int32)
    fp = fpga.decode_batch(ints)
    if not np.array_equal(cpu, fp):
        mism = np.where(cpu != fp)[0][:5]
        raise AssertionError(
            f"CPU/FPGA mismatch at indices {mism.tolist()} "
            f"(cpu={cpu[mism].tolist()} fpga={fp[mism].tolist()}). "
            f"Bitstream likely stale — re-synthesize."
        )
    print("Correctness gate: CPU and FPGA agree on all syndromes. OK\n")


# ------------------------------------------------------------------
# Benchmarks
# ------------------------------------------------------------------
def bench_cpu_single(strs, reps=200_000):
    sample = strs[:1000]
    for s in sample:                 # warmup
        cpu_lookup_decode(s)
    # amortized: timer overhead would swamp a single dict lookup
    t0 = time.perf_counter_ns()
    for i in range(reps):
        cpu_lookup_decode(sample[i % len(sample)])
    t1 = time.perf_counter_ns()
    return (t1 - t0) / reps          # ns per decode (amortized)


def bench_fpga_single(fpga, ints, reps=2000):
    one = ints[:1].copy()
    for _ in range(50):              # warmup
        fpga.decode_batch(one)
    times = []
    for i in range(reps):
        one[0] = ints[i % len(ints)]
        t0 = time.perf_counter_ns()
        fpga.decode_batch(one)
        t1 = time.perf_counter_ns()
        times.append(t1 - t0)
    return times                     # per-call round-trip, ns


def bench_cpu_throughput(strs):
    for s in strs[:1000]:            # warmup
        cpu_lookup_decode(s)
    t0 = time.perf_counter_ns()
    _ = [cpu_lookup_decode(s) for s in strs]
    t1 = time.perf_counter_ns()
    return len(strs) / ((t1 - t0) / 1e9)   # decodes/sec


def bench_fpga_throughput(fpga, ints):
    fpga.decode_batch(ints[:min(1000, len(ints))])  # warmup
    _, parts = fpga.decode_batch(ints, timing=True)
    total_ns = parts["xfer_in"] + parts["kernel"] + parts["xfer_out"]
    return len(ints) / (total_ns / 1e9), parts


# ------------------------------------------------------------------
# Image saving
# ------------------------------------------------------------------
def ensure_bench_dir():
    os.makedirs("results/benchmarks", exist_ok=True)


def _stamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def save_latency_plot(cpu_lat_ns, fpga_lat_ns_list):
    """Single-decode latency: CPU vs FPGA. Log scale (range spans ~1000x)."""
    ensure_bench_dir()
    fpga_median = statistics.median(fpga_lat_ns_list)

    fig, ax = plt.subplots(figsize=(7, 5))
    labels = ["CPU\n(dict lookup)", "FPGA\n(PCIe round-trip)"]
    values_us = [cpu_lat_ns / 1000, fpga_median / 1000]
    bars = ax.bar(labels, values_us, color=["#4C78A8", "#E45756"])

    ax.set_yscale("log")
    ax.set_ylabel("Latency per decode (microseconds, log scale)")
    ax.set_title("Single-Decode Latency: CPU vs FPGA\n(lower is better)")
    for b, v in zip(bars, values_us):
        ax.text(b.get_x() + b.get_width() / 2, v,
                f"{v:.3f} us" if v >= 0.01 else f"{v*1000:.1f} ns",
                ha="center", va="bottom", fontsize=9)
    ax.text(0.5, -0.18,
            "CPU wins single-decode: a 4-bit lookup is dwarfed by PCIe transfer overhead.",
            transform=ax.transAxes, ha="center", fontsize=8, color="gray")

    path = f"benchmarks/results/benchmarks/latency_single_{_stamp()}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def save_throughput_plot(cpu_tput, fpga_tput):
    """Batch throughput: CPU vs FPGA (decodes/sec, amortized)."""
    ensure_bench_dir()
    fig, ax = plt.subplots(figsize=(7, 5))
    labels = ["CPU\n(sequential)", "FPGA\n(batched, 1 round-trip)"]
    values = [cpu_tput / 1e6, fpga_tput / 1e6]
    bars = ax.bar(labels, values, color=["#4C78A8", "#54A24B"])

    ax.set_ylabel("Throughput (million decodes / sec, higher is better)")
    ax.set_title("Batch Throughput: CPU vs FPGA")
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f} M/s",
                ha="center", va="bottom", fontsize=9)

    winner = "FPGA" if fpga_tput > cpu_tput else "CPU"
    ax.text(0.5, -0.18,
            f"Amortized over the batch, {winner} has higher throughput on this workload.",
            transform=ax.transAxes, ha="center", fontsize=8, color="gray")

    path = f"benchmarks/results/benchmarks/throughput_batch_{_stamp()}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def save_fpga_breakdown_plot(parts):
    """Where FPGA batch time goes: transfer-in / kernel / transfer-out."""
    ensure_bench_dir()
    fig, ax = plt.subplots(figsize=(7, 5))
    labels = ["transfer-in", "kernel\n(host-observed)", "transfer-out"]
    values_us = [parts["xfer_in"] / 1000, parts["kernel"] / 1000,
                 parts["xfer_out"] / 1000]
    bars = ax.bar(labels, values_us,
                  color=["#B279A2", "#F58518", "#B279A2"])

    ax.set_ylabel("Time (microseconds)")
    ax.set_title("FPGA Batch Time Breakdown\n(kernel figure includes XRT dispatch, not raw compute)")
    for b, v in zip(bars, values_us):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f} us",
                ha="center", va="bottom", fontsize=9)

    path = f"benchmarks/results/benchmarks/fpga_breakdown_{_stamp()}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    N = 100_000
    ints, strs = make_syndromes(N)

    print("=" * 60)
    print("Lookup Decoder Benchmark  (CPU vs FPGA)")
    print("=" * 60)
    print(f"Syndromes: {N}\n")

    # ---- CPU (always available) ----
    cpu_lat = bench_cpu_single(strs)
    cpu_tput = bench_cpu_throughput(strs)
    print("CPU (pure-Python dict lookup)")
    print(f"  single-decode latency (amortized): {cpu_lat:8.1f} ns")
    print(f"  throughput:                        {cpu_tput/1e6:8.2f} M decodes/s\n")

    if not PYXRT_AVAILABLE:
        print("pyxrt unavailable — skipping FPGA. Source the XRT environment.")
        print("(CPU-only run: no comparison images generated.)")
        return

    fpga = FPGABatchDecoder(max_n=N)
    verify(ints, strs, fpga)

    # ---- FPGA single-decode latency ----
    fl = bench_fpga_single(fpga, ints)
    print("FPGA single-decode (one syndrome per PCIe round-trip)")
    print(f"  median latency: {statistics.median(fl)/1000:8.2f} us")
    print(f"  p90 latency:    {statistics.quantiles(fl, n=10)[8]/1000:8.2f} us")
    print(f"  min latency:    {min(fl)/1000:8.2f} us\n")

    # ---- FPGA batch throughput + kernel-only breakdown ----
    ft, parts = bench_fpga_throughput(fpga, ints)
    print(f"FPGA batch ({N} syndromes in ONE round-trip)")
    print(f"  throughput:              {ft/1e6:8.2f} M decodes/s")
    print(f"  transfer-in:    {parts['xfer_in']/1000:8.2f} us")
    print(f"  kernel(host-observed):   {parts['kernel']/1000:8.2f} us")
    print(f"  transfer-out:   {parts['xfer_out']/1000:8.2f} us\n")

    print("Interpretation:")
    print(f"  single-decode: CPU ~{cpu_lat:.0f} ns vs FPGA "
          f"~{statistics.median(fl)/1000:.1f} us  -> CPU wins (PCIe overhead)")
    print(f"  batch:         CPU {cpu_tput/1e6:.2f} vs FPGA {ft/1e6:.2f} M/s "
          f"-> compare amortized\n")

    # ---- Save benchmark images ----
    p1 = save_latency_plot(cpu_lat, fl)
    p2 = save_throughput_plot(cpu_tput, ft)
    p3 = save_fpga_breakdown_plot(parts)
    print("Saved benchmark images:")
    for p in (p1, p2, p3):
        print(f"  {p}")


if __name__ == "__main__":
    main()