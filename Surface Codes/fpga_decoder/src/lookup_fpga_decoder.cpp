// fpga_decoder/src/lookup_fpga.cpp
//
// FPGA lookup-table decoder for the d=3 surface code.
//
// Input:
//   syndromes[i]   : 4-bit syndrome encoded as an integer (0-15),
//                    with S0 as the most-significant bit:
//                    s = s0*8 + s1*4 + s2*2 + s3*1
//
// Output:
//   corrections[i] : data qubit index to correct
//                    -1 means "no correction"
//
// NOTE: This table is derived from the CORRECTED d=3 geometry in
//       surface_code/config.py (Z_STABILIZERS). It must be regenerated
//       if that geometry changes. Requires re-synthesis of the .xclbin
//       to take effect on hardware.
//
// Example:
//   syndrome = 6 (0b0110) -> correction = 4
//

extern "C" {

void qec_decoder(
    const int* syndromes,
    int* corrections,
    int N
) {
#pragma HLS INTERFACE m_axi     port=syndromes   offset=slave bundle=gmem
#pragma HLS INTERFACE m_axi     port=corrections offset=slave bundle=gmem

#pragma HLS INTERFACE s_axilite port=syndromes   bundle=control
#pragma HLS INTERFACE s_axilite port=corrections bundle=control
#pragma HLS INTERFACE s_axilite port=N           bundle=control
#pragma HLS INTERFACE s_axilite port=return      bundle=control

    // Process one syndrome per loop iteration
    for (int i = 0; i < N; i++) {
#pragma HLS PIPELINE II=1

        int s = syndromes[i];
        int correction = -1;

        // Lookup table: syndrome integer -> data qubit
        // Derived from corrected Z_STABILIZERS (S0 = MSB).
        // Collisions: q1/q2 -> 4 (q1 kept), q6/q7 -> 2 (q6 kept),
        // matching build_lookup_table() in lookup_decoder.py.
        switch (s) {
            case 0:   correction = -1; break; // 0000 -> no error
            case 8:   correction = 0;  break; // 1000 -> q0
            case 4:   correction = 1;  break; // 0100 -> q1
            case 10:  correction = 3;  break; // 1010 -> q3
            case 6:   correction = 4;  break; // 0110 -> q4
            case 5:   correction = 5;  break; // 0101 -> q5
            case 2:   correction = 6;  break; // 0010 -> q6
            case 1:   correction = 8;  break; // 0001 -> q8
            default:  correction = -1; break; // unknown / degenerate-lost
        }

        corrections[i] = correction;
    }
}

} // extern "C"