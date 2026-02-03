# 🔎 Dependency Checker (Archived)

A small Python utility for **verifying whether required dependencies are installed** in the current environment.

This project is archived and represents an early exploration into dependency validation and environment sanity checks.

---

## 🚀 What problem does this solve?

Python scripts often fail at runtime because:
- a dependency is missing
- the environment isn’t what you expect
- assumptions were made instead of checks

This tool answers a simple question:

> “Are the required packages actually installed?”

---

## ✨ What it does

- Checks for the presence of required Python packages
- Reports missing dependencies clearly
- Helps diagnose environment mismatches before runtime errors occur

This tool does **not** install packages or manage environments — it only verifies state.

---

## ▶️ Usage

```bash
python dependency_checker.py
```
(Dependencies to check are defined in the script.)

## 🧠 Design philosophy

- Explicit checks over assumptions
- Simple validation instead of automation
- Fail early, fail clearly

This project pairs naturally with tools that discover dependencies by adding a verification step.

## ⚠️ Project status

Archived / Utility Prototype

- Minimal by design
- No CLI flags
- No environment isolation
- Preserved as a focused learning artifact

## 📜 License

Unlicensed (personal archive).

🏷️ Status
Archived — small, focused, and intentional.