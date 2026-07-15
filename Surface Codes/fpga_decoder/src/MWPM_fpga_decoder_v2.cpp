// fpga_decoder/src/MWPM_fpga_decoder_v2.cpp
//
// Optimization attempt #1 over MWPM_fpga_decoder.cpp.
//
// v1 benchmark result: batch throughput was ~3.3x SLOWER than PyMatching's
// peak CPU speed. Root cause identified: the static dp/parent_i/parent_j
// arrays were shared across every syndrome in the batch loop, creating a
// write-after-read dependency that forced full serialization - syndrome
// s+1 could not begin until syndrome s's reconstruction finished reading
// the same BRAM banks.
//
// This version double-buffers those three arrays (ping-pong on s&1), with
// each buffer fully bank-separated via ARRAY_PARTITION, removing that
// false dependency.
//
// ALGORITHMIC LOGIC IS UNCHANGED from the verified v1 kernel. Only
// storage/pragma structure changed. Must be re-verified via csim before
// synthesis - same discipline as v1. Whether this actually closes the
// speed gap is an open, empirical question; that's what benchmarking
// this version will tell us.

#include "../tables/mwpm_tables.h"

extern "C" {

void qec_mwpm_decoder(
    const int* active_nodes,
    unsigned int* corrections,
    int N
) {
#pragma HLS INTERFACE m_axi     port=active_nodes offset=slave bundle=gmem
#pragma HLS INTERFACE m_axi     port=corrections  offset=slave bundle=gmem
#pragma HLS INTERFACE s_axilite port=active_nodes bundle=control
#pragma HLS INTERFACE s_axilite port=corrections  bundle=control
#pragma HLS INTERFACE s_axilite port=N            bundle=control
#pragma HLS INTERFACE s_axilite port=return       bundle=control

    // Double-buffered DP storage: buffer[0] / buffer[1], selected by s&1.
    // dim=1 complete partition splits this into two physically separate
    // BRAM regions, so consecutive syndromes no longer contend for the
    // same memory port.
    static int   dp[2][DP_STATES];
    static short parent_i[2][DP_STATES];
    static short parent_j[2][DP_STATES];
#pragma HLS ARRAY_PARTITION variable=dp        dim=1 type=complete
#pragma HLS ARRAY_PARTITION variable=parent_i  dim=1 type=complete
#pragma HLS ARRAY_PARTITION variable=parent_j  dim=1 type=complete
#pragma HLS BIND_STORAGE variable=dp        type=RAM_2P impl=BRAM
#pragma HLS BIND_STORAGE variable=parent_i  type=RAM_2P impl=BRAM
#pragma HLS BIND_STORAGE variable=parent_j  type=RAM_2P impl=BRAM

    for (int s = 0; s < N; s++) {

        const int buf = s & 1;

        // ------------------------------------------------------------
        // 1. Read active defects + count real ones
        // ------------------------------------------------------------
        int active[MAX_ACTIVE_DEFECTS];
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
        // 2. Build the DP node list
        // ------------------------------------------------------------
        const int n = 2 * k;
        int node_id[MAX_DP_NODES];
        for (int i = 0; i < MAX_DP_NODES; i++) {
            if (i < k)       node_id[i] = active[i];
            else if (i < n)  node_id[i] = BOUNDARY_IDX;
            else             node_id[i] = -1;
        }

        // ------------------------------------------------------------
        // 3. Bitmask DP on buffer `buf`
        // ------------------------------------------------------------
        const int NUM_STATES = 1 << MAX_DP_NODES;
        const int INF = 0x3fffffff;
        const int full_mask = (1 << n) - 1;

        for (int m = 0; m <= full_mask; m++) {
#pragma HLS PIPELINE II=1
            dp[buf][m] = INF;
        }
        dp[buf][0] = 0;

        for (int mask = 0; mask < NUM_STATES; mask++) {
            if (mask > full_mask) break;
            if (dp[buf][mask] == INF) continue;

            int i = -1;
            for (int b = 0; b < MAX_DP_NODES; b++) {
#pragma HLS UNROLL
                if (i == -1 && b < n && !(mask & (1 << b))) i = b;
            }
            if (i == -1) continue;

            for (int j = 0; j < MAX_DP_NODES; j++) {
#pragma HLS PIPELINE II=1
                if (j <= i || j >= n) continue;
                if (mask & (1 << j)) continue;

                int a = node_id[i];
                int b = node_id[j];
                int w = (a == BOUNDARY_IDX && b == BOUNDARY_IDX) ? 0
                                                                 : DIST_TABLE[a][b];

                int cost = dp[buf][mask] + w;
                int new_mask = mask | (1 << i) | (1 << j);
                if (cost < dp[buf][new_mask]) {
                    dp[buf][new_mask] = cost;
                    parent_i[buf][new_mask] = (short)i;
                    parent_j[buf][new_mask] = (short)j;
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
            int i = parent_i[buf][mask];
            int j = parent_j[buf][mask];
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