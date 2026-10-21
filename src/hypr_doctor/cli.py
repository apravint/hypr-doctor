"""
CLI Entrypoint for hypr-doctor
"""

import sys
import os
import stat
import json
import argparse
import subprocess
from .doctor import HyprDoctor

HOOK_TEMPLATE = """#!/usr/bin/env bash
# Installed by hypr-doctor
set -euo pipefail

echo "🩺 Running hypr-doctor configuration check..."

if command -v hypr-doctor >/dev/null 2>&1; then
    hypr-doctor --strict
else
    python3 -m hypr_doctor.cli --strict
fi

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ git commit halted: hyprland.conf contains conflicting binds or syntax errors."
    exit 1
fi

echo "✅ hyprland.conf verified clean. Proceeding with commit."
exit 0
"""

def install_hook(target_dir: str = ".") -> bool:
    git_dir = os.path.join(os.path.abspath(target_dir), ".git")
    if not os.path.isdir(git_dir):
        print(f"Error: Not a git repository: {target_dir}", file=sys.stderr)
        return False

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "pre-commit")

    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(HOOK_TEMPLATE)

    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"✅ Installed executable pre-commit hook: {hook_path}")
    return True

def main():
    parser = argparse.ArgumentParser(
        prog="hypr-doctor",
        description="Hyprland Configuration Diagnostic & Duplicate Keybinding Linter"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Audit command (default)
    audit_parser = subparsers.add_parser("check", help="Audit hyprland.conf for duplicate binds and errors")
    audit_parser.add_argument("path", nargs="?", default="", help="Path to hyprland.conf (default: ~/.config/hypr/hyprland.conf)")
    audit_parser.add_argument("--json", action="store_true", help="Output JSON results")
    audit_parser.add_argument("--strict", action="store_true", help="Exit non-zero on any warnings or critical issues")

    # Reload command (audit + hyprctl reload)
    reload_parser = subparsers.add_parser("reload", help="Audit config and reload Hyprland if clean")
    reload_parser.add_argument("path", nargs="?", default="", help="Path to hyprland.conf")

    # Hook install command
    hook_parser = subparsers.add_parser("install-hook", help="Install git pre-commit hook into dotfiles repository")
    hook_parser.add_argument("path", nargs="?", default=".", help="Target git repository path")

    args = parser.parse_args()

    if args.command == "install-hook":
        success = install_hook(args.path)
        sys.exit(0 if success else 1)

    # Resolve target config
    path = getattr(args, "path", "") or ""
    as_json = getattr(args, "json", False)
    strict = getattr(args, "strict", False)

    doctor = HyprDoctor(path)
    try:
        report = doctor.audit()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(doctor.format_report(report))

    if args.command == "reload":
        if report["summary"]["critical"] > 0:
            print("❌ Cannot reload Hyprland: Critical errors detected.", file=sys.stderr)
            sys.exit(1)
        res = subprocess.run(["hyprctl", "reload"], capture_output=True, text=True)
        print(f"⚡ Hyprland Reload: {res.stdout.strip()}")
        sys.exit(0)

    # Check exit code threshold
    if strict and (report["summary"]["critical"] > 0 or report["summary"]["warning"] > 0):
        sys.exit(1)
    elif report["summary"]["critical"] > 0:
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()
