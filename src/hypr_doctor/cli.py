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
    hypr-doctor check --strict
else
    python3 -m hypr_doctor.cli check --strict
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
    # Global flags available without subcommands
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any warnings or critical issues")
    parser.add_argument("--fix", action="store_true", help="Automatically comment out or remap duplicate keybindings with safe backups")
    parser.add_argument("--strategy", choices=["comment", "remap"], default="comment", help="Remediation strategy (default: comment)")
    parser.add_argument("--reload", action="store_true", help="Reload Hyprland via hyprctl after check or fix")

    subparsers = parser.add_subparsers(dest="command")

    # Audit command (default)
    audit_parser = subparsers.add_parser("check", help="Audit hyprland.conf for duplicate binds and errors")
    audit_parser.add_argument("path", nargs="?", default="", help="Path to hyprland.conf (default: ~/.config/hypr/hyprland.conf)")
    audit_parser.add_argument("--json", action="store_true", help="Output JSON results")
    audit_parser.add_argument("--strict", action="store_true", help="Exit non-zero on any warnings or critical issues")
    audit_parser.add_argument("--fix", action="store_true", help="Automatically fix duplicate keybindings")
    audit_parser.add_argument("--strategy", choices=["comment", "remap"], default="comment", help="Fix strategy")

    # Fix command
    fix_parser = subparsers.add_parser("fix", help="Automatically comment out or remap duplicate keybindings with safe backups")
    fix_parser.add_argument("path", nargs="?", default="", help="Path to hyprland.conf")
    fix_parser.add_argument("--strategy", choices=["comment", "remap"], default="comment", help="Remediation strategy (default: comment)")
    fix_parser.add_argument("--reload", action="store_true", help="Reload Hyprland via hyprctl after fixing")
    fix_parser.add_argument("--json", action="store_true", help="Output JSON results")

    # Reload command (audit + hyprctl reload)
    reload_parser = subparsers.add_parser("reload", help="Audit config and reload Hyprland if clean")
    reload_parser.add_argument("path", nargs="?", default="", help="Path to hyprland.conf")
    reload_parser.add_argument("--fix", action="store_true", help="Fix duplicates before reloading")
    reload_parser.add_argument("--strategy", choices=["comment", "remap"], default="comment", help="Fix strategy")

    # Hook install command
    hook_parser = subparsers.add_parser("install-hook", help="Install git pre-commit hook into dotfiles repository")
    hook_parser.add_argument("path", nargs="?", default=".", help="Target git repository path")

    # Fallback positional path for root parser
    parser.add_argument("path", nargs="?", default="", help="Path to hyprland.conf (default: ~/.config/hypr/hyprland.conf)")

    args = parser.parse_args()

    if args.command == "install-hook":
        success = install_hook(args.path)
        sys.exit(0 if success else 1)

    path = getattr(args, "path", "") or ""
    as_json = getattr(args, "json", False)
    strict = getattr(args, "strict", False)
    should_fix = (args.command == "fix") or getattr(args, "fix", False)
    strategy = getattr(args, "strategy", "comment")
    should_reload = (args.command == "reload") or getattr(args, "reload", False)

    doctor = HyprDoctor(path)

    # If fix is requested
    if should_fix:
        try:
            fix_res = doctor.fix(strategy=strategy, reload_hyprland=should_reload)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if as_json:
            print(json.dumps(fix_res, indent=2))
        else:
            print("=" * 76)
            print("🛠️ HYPR-DOCTOR AUTO-REMEDIATION")
            print(f"Strategy: {strategy.upper()} | Fixed: {fix_res['fixed_count']} issue(s)")
            print("=" * 76)
            for bak in fix_res["backups"]:
                print(f"📦 Backup:   {bak}")
            for mf in fix_res["files_modified"]:
                print(f"✏️ Modified: {mf}")
            if fix_res.get("reload"):
                print(f"⚡ Hyprland: {fix_res['reload']}")
            print(f"Result: {fix_res['message']}")
            print("=" * 76)

        sys.exit(0)

    # Audit execution
    try:
        report = doctor.audit()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(doctor.format_report(report))

    if should_reload:
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
