import os
import sys


def double_value(number):
    """Return the given number multiplied by two."""
    if not isinstance(number, (int, float)):
        raise TypeError("Input must be a number")

    return number * 2


def main():
    values = [1, 2, 3, 4, 5]

    doubled_values = [double_value(value) for value in values]

    print("Original values:", values)
    print("Doubled values:", doubled_values)


if __name__ == "__main__":
    main()