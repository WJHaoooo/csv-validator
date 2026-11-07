"""Command-line entry point for the project scaffold."""

import argparse


def main() -> int:
    """Parse the help-only CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Configurable CSV Validator & Converter: project scaffold only. "
            "CSV validation and conversion are not implemented yet."
        ),
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
