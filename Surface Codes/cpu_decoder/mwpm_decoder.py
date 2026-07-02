import numpy as np
import pymatching
from surface_code.config import Z_STABILIZERS, NUM_DATA


def build_check_matrix(stabilizers=Z_STABILIZERS, num_data=NUM_DATA):
    """
    Z-stabilizer parity check matrix H.
    H[s, q] = 1 if data qubit q is in stabilizer s.
    Rows = stabilizers (detectors), columns = data qubits (fault_ids).
    """
    H = np.zeros((len(stabilizers), num_data), dtype=np.uint8)
    for s, qubits in enumerate(stabilizers):
        for q in qubits:
            H[s, q] = 1
    return H


class MWPMDecoder:
    """
    Spatial MWPM decoder for X errors (from Z-stabilizer syndrome).
    Built from the check matrix so PyMatching handles boundary
    edges and fault_ids automatically.
    """

    def __init__(self, stabilizers=Z_STABILIZERS, num_data=NUM_DATA):
        self.H = build_check_matrix(stabilizers, num_data)
        self.matching = pymatching.Matching.from_check_matrix(self.H)

    def decode(self, syndrome):
        """
        syndrome : str like "0110" or 1D array of length num_stabilizers.
        Returns  : correction array of length num_data;
                   correction[q] == 1 means apply X to data qubit q.
        """
        if isinstance(syndrome, str):
            syndrome = np.array([int(b) for b in syndrome], dtype=np.uint8)
        else:
            syndrome = np.asarray(syndrome, dtype=np.uint8)
        return self.matching.decode(syndrome)

    def decode_to_qubits(self, syndrome):
        """Return the list of data qubits the decoder wants to correct."""
        correction = self.decode(syndrome)
        return [q for q, bit in enumerate(correction) if bit]
    # ---- Repeated-round (spacetime) decoding -------------------

    def build_spacetime(self, rounds, timelike_weight=None):
        """Build a repetitions=rounds matching graph (spatial + time edges)."""
        kwargs = {"repetitions": rounds}
        if timelike_weight is not None:
            kwargs["timelike_weights"] = timelike_weight
        self._st = pymatching.Matching.from_check_matrix(self.H, **kwargs)
        self._st_rounds = rounds
        return self._st

    def difference_syndrome(self, round_syndromes):
        """
        Per-round syndromes (list[str]) -> (num_stab x T) difference syndrome.
        Column t = syndrome[t] XOR syndrome[t-1], with syndrome[-1] = reset (0).
        """
        T = len(round_syndromes)
        arr = np.zeros((self.H.shape[0], T), dtype=np.uint8)
        prev = np.zeros(self.H.shape[0], dtype=np.uint8)
        for t, s in enumerate(round_syndromes):
            cur = np.array([int(b) for b in s], dtype=np.uint8)
            arr[:, t] = cur ^ prev
            prev = cur
        return arr

    def decode_multi_round(self, round_syndromes, timelike_weight=None):
        """Decode per-round syndromes over the spacetime graph."""
        T = len(round_syndromes)
        if getattr(self, "_st_rounds", None) != T:
            self.build_spacetime(T, timelike_weight)
        syndrome = self.difference_syndrome(round_syndromes)
        return self._st.decode(syndrome)

    def decode_multi_round_to_qubits(self, round_syndromes, timelike_weight=None):
        c = self.decode_multi_round(round_syndromes, timelike_weight)
        return [q for q, bit in enumerate(c) if bit]
    
_default_decoder = MWPMDecoder()

def decode(syndrome):
    """Module-level single-round decode; returns a length-9 correction list."""
    return list(_default_decoder.decode(syndrome))