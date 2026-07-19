#!/usr/bin/env python3
"""Dev-tool: verify panel/init_db.py's _vNNN migration functions are sane.

migrate() dispatches by looking up `_v{ver}` in the module namespace for
every ver from the stored db_version up to MAX_DB_VERSION - a missing
number is just skipped (gaps are fine), but Python silently lets a later
`def _vN(): ...` redefinition shadow an earlier one with the same name,
so a duplicate is a real, silent bug: the first migration's body never
runs for anyone who already passed that version. This script parses the
file's AST (no import, no side effects) and fails loudly on:
  - a duplicate `_vN` function name at module level
  - MAX_DB_VERSION lower than the highest defined `_vN`

Usage:
    python3 common/check_migrations.py <path-to-init_db.py> [<path> ...]

Run this against the DESTINATION branch's init_db.py before cherry-picking
a migration onto it - the two branches have independently diverged
_vNNN numbering, so a number that's free on one branch may already be
taken on the other (see PROJECT_SPEC.md ss3.5/ss5.4).
"""
import ast
import re
import sys

VERSION_FUNC_RE = re.compile(r"^_v(\d+)$")


def check_file(path: str) -> bool:
    # utf-8-sig transparently strips a leading BOM if present (init_db.py has
    # one) - real `import`/compile-from-file handles this automatically, but
    # ast.parse() on a pre-read string does not, and chokes on U+FEFF.
    with open(path, "r", encoding="utf-8-sig") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)

    seen: dict[str, list[int]] = {}
    max_ver = None
    max_ver_line = None
    max_db_version = None
    max_db_version_line = None

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MAX_DB_VERSION":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                        max_db_version = node.value.value
                        max_db_version_line = node.lineno
        if isinstance(node, ast.FunctionDef):
            m = VERSION_FUNC_RE.match(node.name)
            if not m:
                continue
            seen.setdefault(node.name, []).append(node.lineno)
            ver = int(m.group(1))
            if max_ver is None or ver > max_ver:
                max_ver = ver
                max_ver_line = node.lineno

    ok = True

    duplicates = {name: lines for name, lines in seen.items() if len(lines) > 1}
    if duplicates:
        ok = False
        print(f"[FAIL] {path}: duplicate migration function name(s):")
        for name, lines in sorted(duplicates.items()):
            print(f"    {name} defined at lines {lines} - only the LAST one ever runs, "
                  f"the earlier definition's body is silently dead code")

    if max_db_version is None:
        ok = False
        print(f"[FAIL] {path}: could not find a literal-int MAX_DB_VERSION assignment")
    elif max_ver is not None and max_db_version < max_ver:
        ok = False
        print(f"[FAIL] {path}: MAX_DB_VERSION={max_db_version} (line {max_db_version_line}) "
              f"is lower than the highest defined _v{max_ver} (line {max_ver_line}) - "
              f"that migration will never run")

    if ok:
        print(f"[OK] {path}: {len(seen)} migration functions, no duplicates, "
              f"MAX_DB_VERSION={max_db_version} >= highest _v{max_ver}")

    return ok


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    all_ok = True
    for path in argv:
        if not check_file(path):
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
