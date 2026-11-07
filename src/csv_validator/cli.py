"""Command-line interface for validated CSV-to-JSON conversion."""

import argparse
from collections.abc import Sequence
import sys

from csv_validator.converter import CSVRowError, convert_csv
from csv_validator.csv_reader import CSVHeaderError
from csv_validator.schema import SchemaError, load_schema
from csv_validator.writer import JSONWriteError, check_output_path, write_json


def main(argv: Sequence[str] | None = None) -> int:
    """Convert CSV to JSON; return 1 for expected validation or output errors."""
    parser = argparse.ArgumentParser(
        description="Validate CSV against a custom schema and safely write JSON.",
    )
    parser.add_argument("--csv", required=True, help="Input UTF-8 CSV file")
    parser.add_argument("--schema", required=True, help="Input custom JSON schema file")
    parser.add_argument("--output", required=True, help="New UTF-8 JSON output file (must not exist)")
    args = parser.parse_args(argv)

    try:
        schema = load_schema(args.schema)
        inputs = (args.csv, args.schema)
        output = check_output_path(args.output, input_paths=inputs)
        rows = convert_csv(args.csv, schema)
        write_json(rows, output, input_paths=inputs)
    except (SchemaError, CSVHeaderError, CSVRowError, JSONWriteError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Converted {len(rows)} records to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
