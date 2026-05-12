// fpga_decoder/src/qec_decoder.cpp
//
// FPGA lookup-table decoder for the d=3 surface code.
//
// Input:
//   syndromes[i]   : 4-bit syndrome encoded as an integer (0-15)
//
// Output:
//   corrections[i] : data qubit index to correct
//                    -1 means "no correction"
//
// Example:
//   syndrome = 15 (0b1111) -> correction = 4
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

        // Lookup table:
        // syndrome -> data qubit
        switch (s) {
            case 0:   correction = -1; break; // 0000 -> no error
            case 1:   correction = 0;  break; // 0001
            case 3:   correction = 1;  break; // 0011
            case 2:   correction = 2;  break; // 0010
            case 5:   correction = 3;  break; // 0101
            case 15:  correction = 4;  break; // 1111
            case 10:  correction = 5;  break; // 1010
            case 4:   correction = 6;  break; // 0100
            case 12:  correction = 7;  break; // 1100
            case 8:   correction = 8;  break; // 1000
            default:  correction = -1; break; // unknown syndrome
        }

        corrections[i] = correction;
    }
}

} // extern "C"