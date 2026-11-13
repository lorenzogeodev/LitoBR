#!/usr/bin/env python3
"""Checks the plugin against the QGIS repository rules and builds dist/litobr.zip.

Usage:
    python3 build.py            # check + build (placeholders only warn)
    python3 build.py --release  # same, but fails while e-mail/GitHub placeholders remain
"""
import configparser
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
PLUGIN = ROOT / "litobr"
REQUIRED = ["name", "qgisMinimumVersion", "description", "about", "version", "author", "email", "repository",
            "homepage", "tracker"]
BINARIES = {".so", ".dll", ".pyd", ".exe", ".dylib", ".pyc", ".o", ".a"}
QT5_ENUM = re.compile(
    r"\bQt\.(?!ItemDataRole|ItemFlag|CheckState|Orientation|GlobalColor|PenStyle|AlignmentFlag)[A-Za-z]+\b"
    r"|\.exec_\(|\bPyQt[56]\b")
QGIS_ENUM = re.compile(
    r"\bQgsWkbTypes\.(?:Point|Line|Polygon|Unknown|Null)Geometry\b"
    r"|\bQgis\.(?:Info|Warning|Critical|Success|NoLevel)\b"
    r"|\bQgsMapLayerProxyModel\.\w+Layer\b"
    r"|\bQgsTask\.(?:CanCancel|CancelWithoutPrompt|Hidden|Silent|AllFlags)\b"
    r"|\b(?:QgsBlockingNetworkRequest|QgsVectorFileWriter)\.NoError\b"
    r"|\bQgsVectorFileWriter\.(?:CreateOrOverwriteFile|CreateOrOverwriteLayer|AppendToLayer\w*)\b"
    r"|\bQgsPalLayerSettings\.(?:Line|Curved|Horizontal|Free|OverPoint|AroundPoint|OrderedPositionsAroundPoint)\b")
MAX_BYTES = 20 * 1024 * 1024


def files():
    return sorted(f for f in PLUGIN.rglob("*") if f.is_file() and "__pycache__" not in f.parts
                  and f.suffix != ".pyc")


def check(release):
    errors, warnings = [], []
    meta = configparser.ConfigParser(interpolation=None)
    meta.read(PLUGIN / "metadata.txt", encoding="utf-8")
    g = meta["general"]
    for k in REQUIRED:
        if not g.get(k, "").strip():
            errors.append(f"metadata.txt: missing '{k}'")
    for k in ("homepage", "repository", "tracker"):
        if not g.get(k, "").startswith("https://"):
            errors.append(f"metadata.txt: '{k}' must be an https link")
    if "plugin" in g.get("name", "").lower():
        errors.append("metadata.txt: the name must not contain the word 'plugin'")
    placeholders = [k for k in ("email", "homepage", "repository", "tracker")
                    if "SEU_USUARIO" in g.get(k, "") or "exemplo.com" in g.get(k, "")]
    if placeholders:
        (errors if release else warnings).append(
            "metadata.txt still has placeholders: " + ", ".join(placeholders))
    if "SEU_USUARIO" in (ROOT / "README.md").read_text(encoding="utf-8"):
        (errors if release else warnings).append("README.md still has the SEU_USUARIO placeholder")
    code_version = re.search(r'^VERSAO = "([^"]+)"', (PLUGIN / "dialogo.py").read_text(encoding="utf-8"), re.M)
    if not code_version or code_version.group(1) != g.get("version"):
        errors.append("version in dialogo.py differs from metadata.txt")
    for needed in ("__init__.py", "LICENSE", g.get("icon", "icon.png")):
        if not (PLUGIN / needed).is_file():
            errors.append(f"missing file: litobr/{needed}")
    if "classFactory" not in (PLUGIN / "__init__.py").read_text(encoding="utf-8"):
        errors.append("__init__.py has no classFactory")
    for f in files():
        rel = f.relative_to(ROOT)
        if f.suffix in BINARIES:
            errors.append(f"binary file: {rel}")
        if any(p.startswith(".") for p in rel.parts):
            errors.append(f"hidden file: {rel}")
        if f.suffix == ".py":
            text = f.read_text(encoding="utf-8")
            compile(text, str(f), "exec")
            for n, line in enumerate(text.splitlines(), 1):
                code = line.split("#")[0]
                if QT5_ENUM.search(code) or QGIS_ENUM.search(code):
                    errors.append(f"Qt5-only code (breaks on QGIS 4): {rel}:{n}: {line.strip()}")
                if re.search(r"\b(import|from)\s+(requests|urllib\.request|urllib2)\b", code):
                    errors.append(f"network outside QGIS manager: {rel}:{n}")
                if re.search(r"verify\s*=\s*False|CERT_NONE|(?<![.\w])eval\(|(?<![.\w])exec\(|os\.system|shell\s*=\s*True", code):
                    errors.append(f"unsafe call: {rel}:{n}: {line.strip()}")
    return errors, warnings


def build():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / "litobr.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files():
            z.write(f, f.relative_to(ROOT))
        z.write(ROOT / "README.md", "litobr/README.md")
    return out


def main():
    release = "--release" in sys.argv
    errors, warnings = check(release)
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    if errors:
        sys.exit(1)
    out = build()
    size = out.stat().st_size
    if size > MAX_BYTES:
        sys.exit(f"ERROR package is {size / 1e6:.1f} MB (limit 20 MB)")
    print(f"OK    {out.relative_to(ROOT)}: {size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
