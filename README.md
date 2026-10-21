# 🩺 hypr-doctor

[![CI](https://github.com/apravint/hypr-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/apravint/hypr-doctor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-green.svg)](https://python.org)
[![Hyprland](https://img.shields.io/badge/Hyprland-0.50+-cyan.svg)](https://hyprland.org)

> **Zero-dependency static analysis linter, duplicate keybinding detector, and autostart auditor for Hyprland (`hyprland.conf`).**  
> Never get blinded by the dreaded *"Config error in hyprland.conf"* red banner again.

---

## ⚡ The Problem: Why `hyprland.conf` Breaks Silently

When configuring complex Hyprland setups across multiple dotfile fragments:
1. **Conflicting Binds:** Defining the same modifier + key combo twice (e.g., across global scope, app shortcuts, and window rules) causes unhandled collisions or invalid config banners.
2. **Submap Scope Leaks:** Key combinations defined in submaps (like `resize` or `passthrough`) can bleed into global navigation if not scoped properly.
3. **Broken Autostarts:** `exec-once` commands pointing to missing binaries or outdated paths cause failed startup routines.
4. **Missing Included Sources:** Broken `source = ~/.config/hypr/...` directives fail silently or abort parsing.

---

## 🚀 Key Features

- 🔍 **Duplicate Keybinding Detector:** Parses all `bind`, `bindm`, `binde`, `bindl`, and `bindr` instructions, verifying event types (press vs release) and submap boundaries.
- 💡 **Smart Conflict Remediation:** Suggests available, conflict-free modifier combinations (e.g. `$mainMod CTRL ALT, <key>`).
- 📁 **Recursive Source Inclusion:** Traces nested `source = ...` directives automatically.
- ⚡ **Autostart & Binary Verification:** Validates `exec-once` and `exec` targets against `$PATH` and local disk paths.
- 🛡️ **Git Pre-Commit Hook:** Easily installable hook to block commits with broken Hyprland configs in your dotfiles repo.
- 🔄 **Safe Reloading:** `hypr-doctor reload` verifies syntax before calling `hyprctl reload`.

---

## 📦 Quick Start

### Installation

```bash
pip install hypr-doctor
```

Or install from source:

```bash
git clone https://github.com/apravint/hypr-doctor.git
cd hypr-doctor
pip install -e .
```

### Usage

```bash
# Audit active configuration (~/.config/hypr/hyprland.conf)
hypr-doctor check

# Audit specific file
hypr-doctor check /path/to/hyprland.conf

# Output structured JSON results (for scripts / CI)
hypr-doctor check --json

# Verify and safely reload Hyprland if clean
hypr-doctor reload

# Install git pre-commit hook into your dotfiles repository
hypr-doctor install-hook ~/.dotfiles
```

---

## 🧪 Testing

```bash
python3 -m unittest discover tests
```

---

## 📄 License

MIT License. Designed and maintained by [apravint](https://github.com/apravint).
