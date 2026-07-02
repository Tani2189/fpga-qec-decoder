def parse_error_string(error_string):
    """
    Parse a string representation of errors into a list of tuples.

    Parameters
    ----------
    error_string : str
        Example: "X1,Z4,Y7"

    Returns
    -------
    list
        Example: [("X", 1), ("Z", 4), ("Y", 7)]
    """
    errors = []

    for item in error_string.split(","):

        error_type, qubit = item.split(":")

        errors.append(
            (
                error_type.upper(),
                int(qubit)
            )
        )

    return errors