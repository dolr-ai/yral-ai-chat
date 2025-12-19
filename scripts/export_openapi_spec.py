#!/usr/bin/env python
"""
Export OpenAPI specification to YAML file

Usage:
    python scripts/export_openapi_spec.py
"""
import json
import sys
from pathlib import Path

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.main import app


def export_openapi_spec():
    """Export OpenAPI specification to YAML"""
    # Get OpenAPI schema
    openapi_schema = app.openapi()

    # Create docs/api directory if it doesn't exist
    docs_dir = Path(__file__).parent.parent / "docs" / "api"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Export to YAML
    yaml_path = docs_dir / "openapi.yaml"
    with yaml_path.open("w") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False)

    # Also export to JSON for convenience
    json_path = docs_dir / "openapi.json"
    with json_path.open("w") as f:
        json.dump(openapi_schema, f, indent=2)


    # Print some stats
    len(openapi_schema.get("paths", {}))
    len(openapi_schema.get("components", {}).get("schemas", {}))


if __name__ == "__main__":
    export_openapi_spec()
