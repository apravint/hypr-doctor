"""
HyprDoctor Diagnostic Engine
Parses Hyprland configurations, audits binds across submaps, detects duplicates,
and verifies autostart commands.
"""

import os
import re
import shutil
import string
import datetime
import subprocess
from typing import Dict, List, Any, Optional, Set, Tuple

KNOWN_DISPATCHERS = {
    "exec", "killactive", "closewindow", "workspace", "movetoworkspace",
    "movetoworkspacesilent", "togglefloating", "fullscreen", "pseudo",
    "layoutmsg", "pin", "exit", "togglegroup", "moveoutofgroup",
    "changegroupactive", "resizeactive", "moveactive", "submap",
    "togglespecialworkspace", "swapwindow", "movewindow", "focuswindow",
    "focusmonitor", "movecurrentworkspacetomonitor", "dpms", "pass",
    "sendshortcut", "global", "movefocus", "resizewindow", "alterzorder"
}

class HyprDoctor:
    def __init__(self, config_path: Optional[str] = None):
        if not config_path:
            config_path = os.path.expanduser("~/.config/hypr/hyprland.conf")
        self.config_path = os.path.abspath(os.path.expanduser(config_path))
        self.visited_files: Set[str] = set()

    def audit(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Hyprland configuration not found: {self.config_path}")

        self.visited_files.clear()
        issues: List[Dict[str, Any]] = []
        binds_map: Dict[str, Dict[str, Any]] = {}
        all_binds: List[Dict[str, Any]] = []
        exec_onces: List[Dict[str, Any]] = []
        sources: List[str] = []

        self._parse_file(self.config_path, issues, binds_map, all_binds, exec_onces, sources)

        # Calculate health score
        critical_count = sum(1 for i in issues if i["severity"] == "CRITICAL")
        warning_count = sum(1 for i in issues if i["severity"] == "WARNING")
        info_count = sum(1 for i in issues if i["severity"] == "INFO")

        score = max(0, 100 - (critical_count * 25) - (warning_count * 10) - (info_count * 2))

        return {
            "config_path": self.config_path,
            "health_score": score,
            "total_binds": len(all_binds),
            "total_autostarts": len(exec_onces),
            "sources": sources,
            "summary": {
                "critical": critical_count,
                "warning": warning_count,
                "info": info_count,
                "clean": (critical_count == 0 and warning_count == 0)
            },
            "issues": issues,
            "binds": all_binds
        }

    def _parse_file(
        self,
        path: str,
        issues: List[Dict[str, Any]],
        binds_map: Dict[str, Dict[str, Any]],
        all_binds: List[Dict[str, Any]],
        exec_onces: List[Dict[str, Any]],
        sources: List[str]
    ):
        if path in self.visited_files:
            return
        self.visited_files.add(path)
        sources.append(path)

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            issues.append({
                "severity": "CRITICAL",
                "type": "FILE_READ_ERROR",
                "file": path,
                "line": 0,
                "message": f"Unable to read file: {e}"
            })
            return

        current_submap = "global"

        for line_no, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # Strip inline comments
            clean_line = line.split("#")[0].strip()

            # Handle submaps
            if clean_line.startswith("submap"):
                parts = clean_line.split("=", 1)
                if len(parts) == 2:
                    current_submap = parts[1].strip() or "global"
                continue

            # Handle sources recursively
            if clean_line.startswith("source"):
                parts = clean_line.split("=", 1)
                if len(parts) == 2:
                    sub_path = os.path.expanduser(parts[1].strip())
                    if not os.path.isabs(sub_path):
                        sub_path = os.path.join(os.path.dirname(path), sub_path)
                    if os.path.exists(sub_path):
                        self._parse_file(sub_path, issues, binds_map, all_binds, exec_onces, sources)
                    else:
                        issues.append({
                            "severity": "WARNING",
                            "type": "MISSING_SOURCE",
                            "file": path,
                            "line": line_no,
                            "message": f"Included source file does not exist: {sub_path}"
                        })
                continue

            # Handle exec-once
            if clean_line.startswith("exec-once"):
                parts = clean_line.split("=", 1)
                if len(parts) == 2:
                    cmd_str = parts[1].strip()
                    exec_onces.append({
                        "file": path,
                        "line": line_no,
                        "command": cmd_str
                    })
                    self._validate_exec(cmd_str, path, line_no, issues, is_autostart=True)
                continue

            # Handle binds
            bind_match = re.match(r"^(bind[meilr]?)\s*=\s*(.*)", clean_line)
            if bind_match:
                bind_type = bind_match.group(1)
                payload = bind_match.group(2)
                self._handle_bind(
                    bind_type, payload, current_submap, path, line_no, raw_line,
                    issues, binds_map, all_binds
                )

    def _handle_bind(
        self,
        bind_type: str,
        payload: str,
        submap: str,
        file: str,
        line_no: int,
        raw_line: str,
        issues: List[Dict[str, Any]],
        binds_map: Dict[str, Dict[str, Any]],
        all_binds: List[Dict[str, Any]]
    ):
        parts = [p.strip() for p in payload.split(",", 3)]
        if len(parts) < 3:
            issues.append({
                "severity": "CRITICAL",
                "type": "MALFORMED_BIND",
                "file": file,
                "line": line_no,
                "message": f"Malformed bind syntax (expected at least 3 comma-separated arguments): '{payload}'"
            })
            return

        mods = parts[0]
        key = parts[1]
        dispatcher = parts[2]
        args = parts[3] if len(parts) > 3 else ""

        # Normalize modifier string (e.g. $mainMod ALT -> sort tokens)
        norm_mods = " ".join(sorted(mods.upper().split()))
        key_norm = key.upper()
        event_tag = "[release]" if bind_type == "bindr" else "[press]"
        bind_key = f"[{submap}]{event_tag} {norm_mods} + {key_norm}"

        entry = {
            "file": file,
            "line": line_no,
            "bind_type": bind_type,
            "submap": submap,
            "mods": mods,
            "key": key,
            "combo": bind_key,
            "dispatcher": dispatcher,
            "args": args,
            "raw": raw_line.strip()
        }
        all_binds.append(entry)

        # Check for duplicates
        if bind_key in binds_map:
            prev = binds_map[bind_key]
            issues.append({
                "severity": "CRITICAL",
                "type": "DUPLICATE_BIND",
                "file": file,
                "line": line_no,
                "raw": raw_line.rstrip("\r\n"),
                "bind_key": bind_key,
                "bind_type": bind_type,
                "submap": submap,
                "mods": mods,
                "key": key,
                "dispatcher": dispatcher,
                "args": args,
                "message": f"Conflicting keybind: '{bind_key}' is already bound to '{prev['dispatcher']} {prev['args']}' at line {prev['line']}",
                "previous_file": prev["file"],
                "previous_line": prev["line"],
                "suggestion": self._suggest_free_mod(norm_mods, key_norm)
            })
        else:
            binds_map[bind_key] = entry

        # Check unknown dispatchers
        if dispatcher and dispatcher not in KNOWN_DISPATCHERS and not dispatcher.startswith("submap"):
            issues.append({
                "severity": "WARNING",
                "type": "UNKNOWN_DISPATCHER",
                "file": file,
                "line": line_no,
                "message": f"Unrecognized dispatcher: '{dispatcher}'"
            })

        # Validate executable target
        if dispatcher == "exec" and args:
            self._validate_exec(args, file, line_no, issues, is_autostart=False)

    def _validate_exec(self, cmd_str: str, file: str, line_no: int, issues: List[Dict[str, Any]], is_autostart: bool):
        # Extract first binary / executable token
        first_token = cmd_str.split()[0]
        if first_token in {"[", "test", "exec", "eval", "sh", "bash"}:
            return

        expanded = os.path.expanduser(first_token)
        if expanded.startswith("/"):
            if not os.path.exists(expanded):
                issues.append({
                    "severity": "WARNING",
                    "type": "MISSING_EXECUTABLE",
                    "file": file,
                    "line": line_no,
                    "message": f"{'Autostart' if is_autostart else 'Bind'} executable target does not exist on disk: '{first_token}'"
                })
        else:
            if not shutil.which(first_token):
                issues.append({
                    "severity": "INFO",
                    "type": "BINARY_NOT_IN_PATH",
                    "file": file,
                    "line": line_no,
                    "message": f"Command binary '{first_token}' not currently found in $PATH"
                })

    def _suggest_free_mod(self, norm_mods: str, key: str) -> str:
        candidates = ["$mainMod CTRL ALT", "$mainMod SHIFT ALT", "$mainMod CTRL SHIFT"]
        for c in candidates:
            if norm_mods != " ".join(sorted(c.upper().split())):
                return f"Try assigning to {c}, {key}"
        return f"Try using a dedicated submap or $mainMod CTRL ALT, {key}"

    def fix(self, strategy: str = "comment", reload_hyprland: bool = False) -> Dict[str, Any]:
        """
        Remediate duplicate keybindings automatically with safe timestamped backups.
        strategy: 'comment' (comment out duplicates) or 'remap' (attempt remap to $mainMod CTRL ALT)
        """
        audit_report = self.audit()
        dup_issues = [i for i in audit_report["issues"] if i["type"] == "DUPLICATE_BIND"]

        if not dup_issues:
            return {
                "fixed_count": 0,
                "backups": [],
                "files_modified": [],
                "message": "No duplicate binds detected. Configuration is already clean."
            }

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        files_map: Dict[str, List[Dict[str, Any]]] = {}
        for issue in dup_issues:
            f = issue["file"]
            if f not in files_map:
                files_map[f] = []
            files_map[f].append(issue)

        backups = []
        files_modified = []
        fixed_count = 0
        existing_combos = {b["combo"] for b in audit_report["binds"]}

        for file_path, file_dups in files_map.items():
            if not os.path.exists(file_path):
                continue

            bak_path = f"{file_path}.bak.{ts}"
            shutil.copy2(file_path, bak_path)
            backups.append(bak_path)

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            dups_by_line = {d["line"]: d for d in file_dups}

            new_lines = []
            for line_idx, line in enumerate(lines, 1):
                if line_idx in dups_by_line:
                    dup = dups_by_line[line_idx]
                    prev_line = dup.get("previous_line", "?")
                    submap = dup.get("submap", "global")
                    key = dup.get("key", "")
                    disp = dup.get("dispatcher", "")
                    args = dup.get("args", "")
                    btype = dup.get("bind_type", "bind")

                    if strategy == "remap":
                        candidate_combo = f"[{submap}][press] $MAINMOD CTRL ALT + {key.upper()}"
                        if candidate_combo not in existing_combos:
                            comma_args = f", {args}" if args else ""
                            new_line = f"{btype} = $mainMod CTRL ALT, {key}, {disp}{comma_args}  # [hypr-doctor remapped from duplicate at line {prev_line}]\n"
                            existing_combos.add(candidate_combo)
                            new_lines.append(new_line)
                            fixed_count += 1
                            continue

                    clean_orig = line.rstrip("\r\n")
                    new_line = f"# [hypr-doctor disabled duplicate of line {prev_line}] {clean_orig}\n"
                    new_lines.append(new_line)
                    fixed_count += 1
                else:
                    new_lines.append(line)

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            files_modified.append(file_path)

        reload_output = None
        if reload_hyprland and shutil.which("hyprctl"):
            try:
                res = subprocess.run(["hyprctl", "reload"], capture_output=True, text=True, timeout=5)
                reload_output = res.stdout.strip()
            except Exception as e:
                reload_output = f"Reload failed: {e}"

        return {
            "fixed_count": fixed_count,
            "backups": backups,
            "files_modified": files_modified,
            "reload": reload_output,
            "message": f"Successfully resolved {fixed_count} duplicate keybinding(s)."
        }

    @staticmethod
    def format_report(data: Dict[str, Any]) -> str:
        s = data["summary"]
        report = []
        report.append("=" * 76)
        report.append("🩺 HYPR-DOCTOR: HYPRLAND CONFIGURATION AUDIT REPORT")
        report.append(f"Target: {data['config_path']}")
        report.append(f"Health Score: {data['health_score']}/100 | Binds Audited: {data['total_binds']} | Autostarts: {data['total_autostarts']}")
        report.append(f"Issues: {s['critical']} Critical | {s['warning']} Warnings | {s['info']} Info")
        report.append("=" * 76)

        if s["clean"]:
            report.append("✅ PERFECT HEALTH: Zero duplicate keybindings or critical syntax faults.")
        else:
            for idx, issue in enumerate(data["issues"], 1):
                sev = issue["severity"]
                icon = "❌" if sev == "CRITICAL" else ("⚠️" if sev == "WARNING" else "ℹ️")
                report.append(f"\n[{idx}] {icon} {sev} | {issue['type']} at line {issue['line']}")
                report.append(f"    File:    {issue['file']}")
                report.append(f"    Message: {issue['message']}")
                if issue.get("suggestion"):
                    report.append(f"    Fix:     {issue['suggestion']}")

        report.append("\n" + "=" * 76)
        return "\n".join(report)

def audit_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    return HyprDoctor(config_path).audit()

def fix_config(config_path: Optional[str] = None, strategy: str = "comment", reload_hyprland: bool = False) -> Dict[str, Any]:
    return HyprDoctor(config_path).fix(strategy=strategy, reload_hyprland=reload_hyprland)
