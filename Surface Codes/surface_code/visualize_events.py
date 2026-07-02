import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def plot_detection_events(
    events,
    save_path="results/detection_events.png",
):
    """
    Visualize detection events as a spacetime heatmap.
    """

    data = []

    for event in events:
        row = [int(bit) for bit in event]
        data.append(row)

    data = np.array(data)

    plt.figure(figsize=(6, 4))

    plt.imshow(
        data,
        aspect="auto",
    )

    plt.colorbar(
        label="Detection Event"
    )

    plt.xlabel(
        "Stabilizer Index"
    )

    plt.ylabel(
        "Round"
    )

    plt.title(
        "Surface Code Detection Events"
    )

    plt.xticks(
        range(data.shape[1]),
        [f"S{i}" for i in range(data.shape[1])]
    )

    plt.yticks(
        range(data.shape[0]),
        [f"R{i}" for i in range(data.shape[0])]
    )

    plt.tight_layout()

    Path("results").mkdir(
        exist_ok=True
    )

    plt.savefig(
        save_path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"\nSaved detection-event plot to:\n{save_path}"
    )