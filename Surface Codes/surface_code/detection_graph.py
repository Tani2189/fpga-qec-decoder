def build_detection_graph(events, num_stabilizers=4):
    """
    Build a spacetime detection graph from detection events.

    Parameters
    ----------
    events : list of str
        Per-round detection event bitstrings e.g. ["0000", "1111", "0000"]
    num_stabilizers : int
        Number of Z stabilizers (default 4 for d=3)

    Returns
    -------
    nodes : list of tuples
        (stabilizer_index, round) for every active detection event
    space_edges : list of tuples
        ((s1, r), (s2, r), weight) — adjacent stabilizers, same round
    time_edges : list of tuples
        ((s, r1), (s, r2), weight) — same stabilizer, consecutive rounds
    """
    nodes = []
    for r, event in enumerate(events):
        for s, bit in enumerate(event):
            if bit == "1":
                nodes.append((s, r))

    space_edges = []
    for r, event in enumerate(events):
        for s in range(num_stabilizers - 1):
            space_edges.append(((s, r), (s + 1, r), 1.0))

    time_edges = []
    for r in range(len(events) - 1):
        for s in range(num_stabilizers):
            time_edges.append(((s, r), (s, r + 1), 1.0))

    return nodes, space_edges, time_edges


def get_active_subgraph(nodes, space_edges, time_edges):
    """
    Filter edges to only those connecting active (event=1) nodes.
    This is what gets passed to MWPM.
    """
    node_set = set(nodes)

    active_space = [
        e for e in space_edges
        if e[0] in node_set and e[1] in node_set
    ]
    active_time = [
        e for e in time_edges
        if e[0] in node_set and e[1] in node_set
    ]

    return active_space + active_time

