import csv
import random
import statistics
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from integration.run_decoder_pipeline import (
    FPGALookupDecoder,
)

from surface_code.syndrome_generator import (
    get_syndrome,
    get_syndrome_int,
)

from cpu_decoder.lookup_decoder import (
    decode as cpu_lookup_decode,
)

from cpu_decoder.mwpm_decoder import (
    decode as cpu_mwpm_decode,
)

try:
    from integration.run_decoder_pipeline import (
        FPGALookupDecoder,
    )

    FPGA_AVAILABLE = True

except Exception:

    FPGA_AVAILABLE = False

# ============================================================
# Benchmark Configuration
# ============================================================

NUM_RUNS = 1000

OUTPUT_DIR = Path("benchmarks/results")

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

CSV_FILE = OUTPUT_DIR / "benchmark_results.csv"

PLOT_FILE = OUTPUT_DIR / "benchmark_plot.png"


# ============================================================
# Random X-Error Generator
# ============================================================

def generate_random_x_error():
    """
    Generate a random X error on a random data qubit.
    """

    qubit = random.randint(0, 8)

    syndrome_bitstring = get_syndrome(
        error_qubit=qubit,
        error_type="X",
    )

    syndrome_int = get_syndrome_int(
        error_qubit=qubit,
        error_type="X",
    )

    return (
        qubit,
        syndrome_bitstring,
        syndrome_int,
    )


# ============================================================
# CPU Lookup Benchmark
# ============================================================

def benchmark_cpu_lookup():

    timings = []

    for _ in range(NUM_RUNS):

        (
            _,
            syndrome_bitstring,
            _,
        ) = generate_random_x_error()

        start = time.perf_counter()

        cpu_lookup_decode(
            syndrome_bitstring
        )

        elapsed_us = (
            time.perf_counter() - start
        ) * 1e6

        timings.append(elapsed_us)

    return timings


# ============================================================
# CPU MWPM Benchmark
# ============================================================

def benchmark_cpu_mwpm():

    timings = []

    for _ in range(NUM_RUNS):

        (
            _,
            syndrome_bitstring,
            _,
        ) = generate_random_x_error()

        start = time.perf_counter()

        cpu_mwpm_decode(
            syndrome_bitstring
        )

        elapsed_us = (
            time.perf_counter() - start
        ) * 1e6

        timings.append(elapsed_us)

    return timings


# ============================================================
# FPGA Lookup Benchmark
# ============================================================

def benchmark_fpga_lookup():

    timings = []

    # --------------------------------------------------------
    # IMPORTANT:
    # Initialize FPGA ONCE
    # --------------------------------------------------------
    fpga_decoder = FPGALookupDecoder()

    for _ in range(NUM_RUNS):

        (
            _,
            _,
            syndrome_int,
        ) = generate_random_x_error()

        start = time.perf_counter()

        fpga_decoder.decode(
            syndrome_int
        )

        elapsed_us = (
            time.perf_counter() - start
        ) * 1e6

        timings.append(elapsed_us)

    return timings


# ============================================================
# Statistics Helper
# ============================================================

def compute_stats(name, timings):

    avg = statistics.mean(timings)

    minimum = min(timings)

    maximum = max(timings)

    stddev = statistics.stdev(timings)

    throughput = 1e6 / avg

    return {
        "decoder": name,
        "avg_us": avg,
        "min_us": minimum,
        "max_us": maximum,
        "stddev_us": stddev,
        "throughput": throughput,
    }


# ============================================================
# Save CSV
# ============================================================

def save_csv(stats_list):

    with open(
        CSV_FILE,
        "w",
        newline="",
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "Decoder",
            "Average Latency (us)",
            "Minimum Latency (us)",
            "Maximum Latency (us)",
            "Std Dev (us)",
            "Throughput (decodes/sec)",
        ])

        for stats in stats_list:

            writer.writerow([
                stats["decoder"],
                f"{stats['avg_us']:.3f}",
                f"{stats['min_us']:.3f}",
                f"{stats['max_us']:.3f}",
                f"{stats['stddev_us']:.3f}",
                f"{stats['throughput']:.2f}",
            ])


# ============================================================
# Plot Results
# ============================================================

def generate_plot(stats_list):

    decoder_names = [
        s["decoder"]
        for s in stats_list
    ]

    avg_latencies = [
        s["avg_us"]
        for s in stats_list
    ]

    plt.figure(figsize=(8, 5))

    plt.bar(
        decoder_names,
        avg_latencies,
    )

    plt.ylabel(
        "Average Latency (us)"
    )

    plt.title(
        "QEC Decoder Benchmark"
    )

    plt.tight_layout()

    plt.savefig(PLOT_FILE)

    plt.close()


# ============================================================
# Main Benchmark
# ============================================================

def main():

    print("=" * 60)
    print("Quantum Error Correction Decoder Benchmark")
    print("=" * 60)

    print(f"\nRunning {NUM_RUNS} iterations per decoder...\n")

    # --------------------------------------------------------
    # Store benchmark results
    # --------------------------------------------------------
    stats_list = []

    # --------------------------------------------------------
    # CPU Lookup
    # --------------------------------------------------------
    print("Benchmarking CPU Lookup Decoder...")

    cpu_lookup_timings = benchmark_cpu_lookup()

    cpu_lookup_stats = compute_stats(
        "CPU Lookup",
        cpu_lookup_timings,
    )

    stats_list.append(
        cpu_lookup_stats
    )

    # --------------------------------------------------------
    # CPU MWPM
    # --------------------------------------------------------
    print("Benchmarking CPU MWPM Decoder...")

    cpu_mwpm_timings = benchmark_cpu_mwpm()

    cpu_mwpm_stats = compute_stats(
        "CPU MWPM",
        cpu_mwpm_timings,
    )

    stats_list.append(
        cpu_mwpm_stats
    )

    # --------------------------------------------------------
    # FPGA Lookup
    # --------------------------------------------------------
    if FPGA_AVAILABLE:

        print("Benchmarking FPGA Lookup Decoder...")

        fpga_lookup_timings = benchmark_fpga_lookup()

        fpga_lookup_stats = compute_stats(
            "FPGA Lookup",
            fpga_lookup_timings,
        )

        stats_list.append(
            fpga_lookup_stats
        )

    else:

        print(
            "Skipping FPGA benchmark "
            "(PyXRT or FPGA unavailable)."
        )

    # --------------------------------------------------------
    # Print Results
    # --------------------------------------------------------
    print("\nBenchmark Results\n")

    for stats in stats_list:

        print(
            f"{stats['decoder']}"
        )

        print(
            f"  Average Latency : "
            f"{stats['avg_us']:.3f} us"
        )

        print(
            f"  Minimum Latency : "
            f"{stats['min_us']:.3f} us"
        )

        print(
            f"  Maximum Latency : "
            f"{stats['max_us']:.3f} us"
        )

        print(
            f"  Std Deviation   : "
            f"{stats['stddev_us']:.3f} us"
        )

        print(
            f"  Throughput      : "
            f"{stats['throughput']:.2f} "
            f"decodes/sec"
        )

        print()

    # --------------------------------------------------------
    # Save Results
    # --------------------------------------------------------
    save_csv(stats_list)

    generate_plot(stats_list)

    print(
        f"CSV results saved to:\n"
        f"  {CSV_FILE}"
    )

    print(
        f"\nPlot saved to:\n"
        f"  {PLOT_FILE}"
    )


if __name__ == "__main__":

    main()