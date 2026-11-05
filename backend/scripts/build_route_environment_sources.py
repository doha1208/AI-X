"""Build an audited coordinate descriptor; never infer provenance, hours or completeness.

Run from backend: python -m scripts.build_route_environment_sources --descriptors INPUT --output OUTPUT
The output and all point files must share a containing directory tree.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from app.services.route_environment_sources import load_environment_sources


def build_manifest(descriptor_path: Path, output_path: Path) -> dict:
    if descriptor_path.resolve() == output_path.resolve():
        raise ValueError("Output must differ from the input descriptor")
    payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    records = []
    for original in payload["sources"]:
        record = dict(original)
        point_path = (descriptor_path.parent / record["points_file"]).resolve()
        if not point_path.is_relative_to(output_path.parent.resolve()):
            raise ValueError("Coordinate files must be inside the output descriptor directory")
        record["points_file"] = point_path.relative_to(output_path.parent.resolve()).as_posix()
        record["sha256"] = hashlib.sha256(point_path.read_bytes()).hexdigest()
        records.append(record)
    result = {"schema_version": 1, "sources": records}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=output_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(result, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        if len(load_environment_sources(temporary)) != len(records):
            raise ValueError("Invalid descriptors: estimates, aggregate counts, malformed coordinates or missing provenance")
        temporary.replace(output_path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_manifest(args.descriptors, args.output)
    print(f"Validated {len(result['sources'])} source descriptors; completeness was not inferred.")


if __name__ == "__main__":
    main()
