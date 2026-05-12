from surface_code.syndrome_generator import get_full_syndrome
from cpu_decoder.lookup_decoder import decode as x_decode


def decode_full(error_qubit=None, error_type=None):
    """
    Run the full surface-code decoding pipeline.

    Parameters
    ----------
    error_qubit : int or None
        Data qubit index on which to inject an error.
    error_type : str or None
        'X', 'Y', or 'Z'.

    Returns
    -------
    dict
        {
            'x_syndrome': str,
            'z_syndrome': str,
            'x_correction': int or None,
            'z_correction': None,
        }

    Notes
    -----
    - x_syndrome is decoded using the validated lookup decoder.
    - z_syndrome is returned but not yet uniquely decodable.
    - z_correction is therefore currently None.
    """

    # Generate both syndrome streams
    full = get_full_syndrome(
        error_qubit=error_qubit,
        error_type=error_type,
    )

    x_syndrome = full["x_syndrome"]
    z_syndrome = full["z_syndrome"]

    # Decode X errors using the validated lookup decoder
    x_correction = x_decode(x_syndrome)

    # Placeholder: Z decoding not yet uniquely resolvable
    z_correction = None

    return {
        "x_syndrome": x_syndrome,
        "z_syndrome": z_syndrome,
        "x_correction": x_correction,
        "z_correction": z_correction,
    }
