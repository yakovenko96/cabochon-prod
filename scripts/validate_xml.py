"""Check XML well-formedness only (not Odoo view/schema correctness)."""
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[1]
modules = (root / "addons/cabochon_base", root / "addons/cabochon_manufacturing")
paths = [p for mod in modules for p in mod.rglob("*.xml")]
if not paths:
    raise SystemExit("No XML files found under active modules; check repository layout")
for path in paths:
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        raise SystemExit(f"XML parse error: {path.relative_to(root)}: {exc}") from exc
print(f"XML parse OK: {len(paths)} file(s)")
