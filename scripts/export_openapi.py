#!/usr/bin/env python3
"""Export OpenAPI specs from all FastAPI services into docs/openapi/.

Run from project root:
    python3 scripts/export_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_DIR = ROOT / "docs" / "openapi"
OPENAPI_DIR.mkdir(parents=True, exist_ok=True)

# Mapping: service name -> (service dir, app module path, app object name)
SERVICES = {
    "gateway": ("services/gateway", "app.main", "app"),
    "chat-intent": ("services/chat-intent", "app.main", "app"),
    "expert-recommend": ("services/expert-recommend", "app.main", "app"),
    "discovery-ranking": ("services/discovery-ranking", "app.main", "app"),
    "metadata-ingest": ("services/metadata-ingest", "app.main", "app"),
    "mock-api": ("services/mock-api", "app.main", "app"),
}


def export_service(name: str, svc_dir: str, module_path: str, app_attr: str):
    """Load a FastAPI app and write its OpenAPI JSON."""
    svc_path = str(ROOT / svc_dir)
    sys.path.insert(0, svc_path)
    try:
        mod = __import__(module_path, fromlist=[app_attr])
        app = getattr(mod, app_attr)
        spec = app.openapi()
        out_file = OPENAPI_DIR / f"{name}.openapi.json"
        out_file.write_text(json.dumps(spec, indent=2) + "\n")
        print(f"  ✓ {name} → {out_file.relative_to(ROOT)}")
    except Exception as exc:
        print(f"  ✗ {name}: {exc}")
    finally:
        sys.path.remove(svc_path)
        # Clean up cached modules to avoid cross-service import conflicts
        mods_to_remove = [k for k in sys.modules if k.startswith("app")]
        for k in mods_to_remove:
            del sys.modules[k]


def main():
    print("Exporting OpenAPI specs...")
    for name, (svc_dir, mod_path, attr) in SERVICES.items():
        export_service(name, svc_dir, mod_path, attr)
    print(f"\nOpenAPI specs saved to {OPENAPI_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
