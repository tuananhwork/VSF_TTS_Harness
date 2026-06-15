#!/usr/bin/env python3
"""Validate fenced code blocks inside a generated PRD markdown file.

Mirrors the verification step seen in evidence session local_2fc0fafb: when a PRD
embeds ```yaml / ```json examples (e.g. a proposed schema), confirm they actually
parse before the PRD is handed to the user.

Usage:
    python validate_prd_codeblocks.py path/to/PRD_xxx.md

Exit code 0 = all yaml/json blocks parsed (or none found); 1 = at least one failed.
JSON parsing uses the stdlib; YAML parsing is skipped with a notice if PyYAML is
not installed (so the script never hard-fails just because of a missing dep).
"""
import json
import re
import sys

try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except Exception:  # pragma: no cover - optional dependency
    _HAVE_YAML = False

# Capture the language tag and body of every fenced block.
_FENCE = re.compile(r"```([A-Za-z0-9_+-]*)\n(.*?)```", re.DOTALL)


def validate(path: str) -> int:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()

    blocks = _FENCE.findall(text)
    checked = 0
    failures = 0

    for lang, body in blocks:
        lang = lang.strip().lower()
        if lang in ("yaml", "yml"):
            if not _HAVE_YAML:
                print("SKIP yaml block (PyYAML not installed)")
                continue
            checked += 1
            try:
                yaml.safe_load(body)
                print("OK   yaml block")
            except Exception as exc:  # noqa: BLE001 - report any parse error
                failures += 1
                print("FAIL yaml block: %s" % exc)
        elif lang == "json":
            checked += 1
            try:
                json.loads(body)
                print("OK   json block")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print("FAIL json block: %s" % exc)

    if checked == 0:
        print("No yaml/json blocks to validate — nothing to do.")
        return 0

    print("\n%d block(s) checked, %d failure(s)." % (checked, failures))
    return 1 if failures else 0


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    return validate(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
