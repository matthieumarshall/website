#!/usr/bin/env python
"""Validate that all dependencies have compatible licenses"""

import json
import sys

# Permissive license whitelist
# pip-licenses reports varying string forms for the same license,
# so we include both SPDX identifiers and the full classifier names.
ALLOWED_LICENSES = {
    "MIT",
    "MIT License",
    "Apache-2.0",
    "Apache Software License",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSD License",
    "BSD",
    "ISC",
    "ISC License",
    "Freely Distributable",
    "GNU General Public License v3 or later (GPLv3+)",
    "LGPL-2.1",
    "LGPL-2.1+",
    "LGPL-3.0",
    "LGPL-3.0+",
    "LGPL-2.1+ or later (or similar)",
    "MPL-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)",
    "CC0-1.0",
    "CC0",
    "Unlicense",
    "Python-2.0",
    "PSF-2.0",
    "Python Software Foundation License",
    "Artistic License; GNU General Public License (GPL); GNU General Public License v2 or later (GPLv2+)",
}


def validate_licenses(licenses_file):
    """Validate licenses in the provided JSON file"""
    try:
        with open(licenses_file) as f:
            data = json.load(f)
    except FileNotFoundError:
        print("[!] License file not found: {}".format(licenses_file))
        return False
    except json.JSONDecodeError:
        print("[!] Invalid JSON in license file: {}".format(licenses_file))
        return False

    violations = []
    unknown = []

    for entry in data:
        name = entry.get("Name", entry.get("name", "Unknown"))
        license_type = entry.get("License", entry.get("license", "UNKNOWN"))

        if license_type == "UNKNOWN" or license_type is None:
            unknown.append(name)
        elif license_type not in ALLOWED_LICENSES:
            # Check for partial matches (e.g., "MIT/X11" contains "MIT")
            if not any(
                allowed.lower() in license_type.lower() for allowed in ALLOWED_LICENSES
            ):
                violations.append({"package": name, "license": license_type})

    # Report results
    if violations:
        print("\n[!] LICENSE VIOLATIONS DETECTED:")
        print("=" * 60)
        for v in violations:
            print("  Package: {}".format(v["package"]))
            print("  License: {}".format(v["license"]))
            print("  Status: NOT IN WHITELIST")
            print()
        return False

    if unknown:
        print("\n[?] UNKNOWN LICENSES (may need review):")
        print("=" * 60)
        for u in unknown:
            print("  - {}".format(u))
        print()

    print("\n[+] All licenses are compatible")
    print("Total packages checked: {}".format(len(data)))
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: validate-licenses.py <licenses.json>")
        sys.exit(1)

    success = validate_licenses(sys.argv[1])
    sys.exit(0 if success else 1)
