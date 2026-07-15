// fpga_decoder/src/mwpm_fpga.cpp
//
// Bounded exact MWPM decoder for the d=3 rotated surface code,
// spacetime graph with rounds=4.
//
// Batch interface: N syndromes per call. Each syndrome is a fixed-size
// array of up to MAX_ACTIVE_DEFECTS detector indices (padded with -1).
//
// The DP enumerates all perfect matchings over up to 12 DP nodes
// (2 * MAX_ACTIVE_DEFECTS, doubled for boundary escape copies) and
// keeps the minimum-weight one. Distance and correction tables come
// from mwpm_tables.h, generated offline from PyMatching's graph.
//
// Output: one 32-bit correction bitmask per syndrome (bit q = flip data qubit q).

#include "../tables/mwpm_tables.h"

extern "C" {

void qec_mwpm_decoder(
    const int* active_nodes,    // shape: N * MAX_ACTIVE_DEFECTS, sentinel = -1
    unsigned int* corrections,  // shape: N
    int N
) {
#pragma HLS INTERFACE m_axi     port=active_nodes offset=slave bundle=gmem
#pragma HLS INTERFACE m_axi     port=corrections  offset=slave bundle=gmem
#pragma HLS INTERFACE s_axilite port=active_nodes bundle=control
#pragma HLS INTERFACE s_axilite port=corrections  bundle=control
#pragma HLS INTERFACE s_axilite port=N            bundle=control
#pragma HLS INTERFACE s_axilite port=return       bundle=control

    // Distance/correction ROMs mapped to on-chip memory
#pragma HLS BIND_STORAGE variable=DIST_TABLE type=ROM_2P impl=BRAM
#pragma HLS BIND_STORAGE variable=CORR_TABLE type=ROM_2P impl=BRAM

    // Per-syndrome decode
    for (int s = 0; s < N; s++) {

        // ------------------------------------------------------------
        // 1. Read active defects + count real ones
        // ------------------------------------------------------------
        int active[MAX_ACTIVE_DEFECTS];
// #pragma HLS ARRAY_PARTITION variable=active complete
        int k = 0;
        for (int i = 0; i < MAX_ACTIVE_DEFECTS; i++) {
#pragma HLS PIPELINE II=1
            int v = active_nodes[s * MAX_ACTIVE_DEFECTS + i];
            active[i] = v;
            if (v >= 0) k++;
        }

        if (k == 0) {
            corrections[s] = 0;
            continue;
        }

        // ------------------------------------------------------------
        // 2. Build the DP node list: k real + k boundary copies = 2k
        //    node_id[i]: index into DIST_TABLE. i<k -> real, else BOUNDARY_IDX
        // ------------------------------------------------------------
        const int n = 2 * k;   // even by construction; <= MAX_DP_NODES
        int node_id[MAX_DP_NODES];
// #pragma HLS ARRAY_PARTITION variable=node_id complete
        for (int i = 0; i < MAX_DP_NODES; i++) {
#pragma HLS UNROLL
            if (i < k)       node_id[i] = active[i];
            else if (i < n)  node_id[i] = BOUNDARY_IDX;
            else             node_id[i] = -1;   // unused
        }

        // ------------------------------------------------------------
        // 3. Bitmask DP: dp[mask] = min weight to match nodes in `mask`.
        //    parent[mask] = (i, j) pair chosen last, to reconstruct.
        // ------------------------------------------------------------
        const int NUM_STATES = 1 << MAX_DP_NODES;   // 4096
        const int INF = 0x3fffffff;

        static int dp[DP_STATES];
        static short parent_i[DP_STATES];
        static short parent_j[DP_STATES];
#pragma HLS BIND_STORAGE variable=dp        type=RAM_2P impl=BRAM
#pragma HLS BIND_STORAGE variable=parent_i  type=RAM_2P impl=BRAM
#pragma HLS BIND_STORAGE variable=parent_j  type=RAM_2P impl=BRAM

        const int full_mask = (1 << n) - 1;
        for (int m = 0; m <= full_mask; m++) {
#pragma HLS PIPELINE II=1
            dp[m] = INF;
        }
        dp[0] = 0;

        for (int mask = 0; mask < NUM_STATES; mask++) {
            if (mask > full_mask) break;
            if (dp[mask] == INF) continue;

            // Find first unmatched bit
            int i = -1;
            for (int b = 0; b < MAX_DP_NODES; b++) {
#pragma HLS UNROLL
                if (i == -1 && b < n && !(mask & (1 << b))) i = b;
            }
            if (i == -1) continue;

            // Try pairing i with each later unmatched j
            for (int j = 0; j < MAX_DP_NODES; j++) {
#pragma HLS PIPELINE II=1
                if (j <= i || j >= n) continue;
                if (mask & (1 << j)) continue;

                int a = node_id[i];
                int b = node_id[j];
                int w = (a == BOUNDARY_IDX && b == BOUNDARY_IDX) ? 0
                                                                 : DIST_TABLE[a][b];

                int cost = dp[mask] + w;
                int new_mask = mask | (1 << i) | (1 << j);
                if (cost < dp[new_mask]) {
                    dp[new_mask] = cost;
                    parent_i[new_mask] = (short)i;
                    parent_j[new_mask] = (short)j;
                }
            }
        }

        // ------------------------------------------------------------
        // 4. Reconstruct pairs, XOR corrections
        // ------------------------------------------------------------
        unsigned int correction = 0;
        int mask = full_mask;
        while (mask != 0) {
#pragma HLS PIPELINE
            int i = parent_i[mask];
            int j = parent_j[mask];
            int a = node_id[i];
            int b = node_id[j];
            if (!(a == BOUNDARY_IDX && b == BOUNDARY_IDX)) {
                correction ^= CORR_TABLE[a][b];
            }
            mask ^= (1 << i) | (1 << j);
        }

        corrections[s] = correction;
    }
}

} // extern "C"