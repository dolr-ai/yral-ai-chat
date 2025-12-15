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
    with open(yaml_path, "w") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False)

    # Also export to JSON for convenience
    json_path = docs_dir / "openapi.json"
    with open(json_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print("✅ OpenAPI spec exported successfully!")
    print(f"  - YAML: {yaml_path}")
    print(f"  - JSON: {json_path}")

    # Print some stats
    paths = len(openapi_schema.get("paths", {}))
    components = len(openapi_schema.get("components", {}).get("schemas", {}))
    print("\n📊 Stats:")
    print(f"  - API Paths: {paths}")
    print(f"  - Schema Components: {components}")


if __name__ == "__main__":
    export_openapi_spec()
