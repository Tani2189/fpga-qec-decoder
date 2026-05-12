// fpga_decoder/host/host.cpp
// ------------------------------------------------------------
// Host application for validating the FPGA lookup decoder.
//
// Usage:
//   ./host ../build/decoder_lookup.xclbin
//
// This program:
//   1. Loads the xclbin.
//   2. Programs the FPGA.
//   3. Creates input/output buffers.
//   4. Runs the qec_decoder kernel.
//   5. Verifies all known lookup-table test vectors.
// ------------------------------------------------------------

#include <iostream>
#include <vector>
#include <string>
#include <iomanip>
#include <stdexcept>

#include <xrt/xrt_device.h>
#include <xrt/xrt_kernel.h>
#include <xrt/xrt_bo.h>

int main(int argc, char* argv[]) {
    // --------------------------------------------------------
    // Check command-line arguments
    // --------------------------------------------------------
    if (argc != 2) {
        std::cerr << "Usage: " << argv[0] << " <xclbin>\n";
        std::cerr << "Example: ./host ../build/decoder_lookup.xclbin\n";
        return 1;
    }

    std::string xclbin_path = argv[1];

    // --------------------------------------------------------
    // Test vectors:
    // syndrome -> expected correction qubit
    // --------------------------------------------------------
    std::vector<int> syndromes = {
        0,   // 0000 -> no error
        1,   // 0001 -> qubit 0
        3,   // 0011 -> qubit 1
        2,   // 0010 -> qubit 2
        5,   // 0101 -> qubit 3
        15,  // 1111 -> qubit 4
        10,  // 1010 -> qubit 5
        4,   // 0100 -> qubit 6
        12,  // 1100 -> qubit 7
        8    // 1000 -> qubit 8
    };

    std::vector<int> expected = {
        -1,  // no correction
         0,
         1,
         2,
         3,
         4,
         5,
         6,
         7,
         8
    };

    const int N = static_cast<int>(syndromes.size());
    std::vector<int> corrections(N, 0);

    try {
        // ----------------------------------------------------
        // Open FPGA device 0
        // ----------------------------------------------------
        xrt::device device(0);
        std::cout << "Using FPGA device 0\n";

        // ----------------------------------------------------
        // Load xclbin onto the device
        // ----------------------------------------------------
        auto uuid = device.load_xclbin(xclbin_path);
        std::cout << "Loaded xclbin: " << xclbin_path << "\n";

        // ----------------------------------------------------
        // Open kernel
        // Top-level HLS function name = qec_decoder
        // ----------------------------------------------------
        xrt::kernel kernel(device, uuid, "qec_decoder");
        std::cout << "Opened kernel: qec_decoder\n";

        // ----------------------------------------------------
        // Allocate input/output buffers
        //
        // Kernel arguments:
        //   0 -> syndromes
        //   1 -> corrections
        //   2 -> N
        // ----------------------------------------------------
        xrt::bo in_bo(
            device,
            N * sizeof(int),
            kernel.group_id(0)
        );

        xrt::bo out_bo(
            device,
            N * sizeof(int),
            kernel.group_id(1)
        );

        // ----------------------------------------------------
        // Map device buffers into host memory
        // ----------------------------------------------------
        auto in_map = in_bo.map<int*>();
        auto out_map = out_bo.map<int*>();

        // ----------------------------------------------------
        // Initialize input and output buffers
        // ----------------------------------------------------
        for (int i = 0; i < N; ++i) {
            in_map[i] = syndromes[i];
            out_map[i] = 0;
        }

        // ----------------------------------------------------
        // Transfer input buffer to FPGA
        // ----------------------------------------------------
        in_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);

        // ----------------------------------------------------
        // Launch kernel
        // ----------------------------------------------------
        auto run = kernel(in_bo, out_bo, N);
        run.wait();

        // ----------------------------------------------------
        // Transfer output buffer back to host
        // ----------------------------------------------------
        out_bo.sync(XCL_BO_SYNC_BO_FROM_DEVICE);

        // Copy results into standard vector
        for (int i = 0; i < N; ++i) {
            corrections[i] = out_map[i];
        }

        // ----------------------------------------------------
        // Verify results
        // ----------------------------------------------------
        bool all_passed = true;

        std::cout << "\n===== FPGA DECODER TEST =====\n\n";

        for (int i = 0; i < N; ++i) {
            bool pass = (corrections[i] == expected[i]);

            std::cout
                << "Syndrome "
                << std::setw(2) << syndromes[i]
                << " -> Correction "
                << std::setw(2) << corrections[i]
                << " (expected "
                << std::setw(2) << expected[i]
                << ") "
                << (pass ? "[PASS]" : "[FAIL]")
                << "\n";

            if (!pass) {
                all_passed = false;
            }
        }

        std::cout << "\n";

        if (all_passed) {
            std::cout << "All FPGA tests passed successfully.\n";
            return 0;
        } else {
            std::cout << "Some FPGA tests failed.\n";
            return 1;
        }
    }
    catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
}