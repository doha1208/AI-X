"""Prepare existing local coordinates; no network collection or completeness inference."""
import argparse
from pathlib import Path

from app.core.config import settings
from app.services.route_environment_inputs import prepare_environment_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-directory", type=Path, default=Path("data/osm"))
    parser.add_argument("--catalog", type=Path, default=Path("data/route_source_catalog.json"))
    parser.add_argument("--output-directory", type=Path, default=Path(settings.route_environment_sources_path).parent)
    args = parser.parse_args()
    result = prepare_environment_inputs(args.raw_directory, args.catalog, args.output_directory)
    print(f"Prepared snapshot {result.snapshot_id}: {sum(d.valid_record_count for d in result.diagnostics)} coordinate records")
    for diagnostic in result.diagnostics:
        print(f"{diagnostic.source_id}: {diagnostic.valid_record_count}; {', '.join(diagnostic.reason_codes) or 'eligible'}")


if __name__ == "__main__":
    main()
