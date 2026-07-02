# surface_code/test_circuit_builder.py

from pathlib import Path
from surface_code.circuit_builder import (
    build_single_round_circuit,
    build_multi_round_circuit,
)


def save_circuit_images():
    # --------------------------------------------------
    # Create images directory at project root
    # --------------------------------------------------
    output_dir = Path("images")
    output_dir.mkdir(exist_ok=True)

    # --------------------------------------------------
    # Single-round circuit
    # --------------------------------------------------
    qc_single = build_single_round_circuit(
        error_qubit=4,
        error_type="X"
    )

    fig_single = qc_single.draw(
        output="mpl",
        fold=-1
    )

    single_path = output_dir / "single_round_circuit.png"
    fig_single.savefig(single_path, bbox_inches="tight")
    print(f"Saved: {single_path}")

    # --------------------------------------------------
    # Multi-round circuit
    # --------------------------------------------------
    qc_multi = build_multi_round_circuit(
        rounds=4,
        error_qubit=4,
        error_type="X"
    )

    fig_multi = qc_multi.draw(
        output="mpl",
        fold=-1
    )

    multi_path = output_dir / "multi_round_circuit.png"
    fig_multi.savefig(multi_path, bbox_inches="tight")
    print(f"Saved: {multi_path}")


if __name__ == "__main__":
    save_circuit_images()