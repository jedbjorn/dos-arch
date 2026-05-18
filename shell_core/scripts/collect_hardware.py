#!/usr/bin/env python3
"""collect_hardware — probe the host and record it in user_hardware.

Shell-agnostic: pure Python, no shell one-liners. Gathers hostname, OS,
kernel, CPU, thread count, RAM, discrete GPU + VRAM, and free disk, then
UPSERTs a single row into user_hardware keyed on (user_id, hostname).

The vram_tier column buckets VRAM to a standard size (8/12/24/32/48/128)
so model_sync.py and docs/model-tiers.md can match models to a machine.

Usage:
    python3 shell_core/scripts/collect_hardware.py [--user-id N] [--db PATH]

Linux is the primary target; macOS gets best-effort fallbacks.
"""
import argparse
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "shell_core" / "shell_db.db"

VRAM_TIERS = [8, 12, 24, 32, 48, 128]


def _run(cmd: list[str]) -> str | None:
    """Run a command, return stripped stdout, or None on any failure."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else None
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None


def _os_pretty() -> str:
    osr = Path("/etc/os-release")
    if osr.exists():
        for line in osr.read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    if platform.system() == "Darwin":
        ver = _run(["sw_vers", "-productVersion"]) or ""
        return f"macOS {ver}".strip()
    return platform.system() or "unknown"


def _cpu_model() -> str | None:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    if platform.system() == "Darwin":
        return _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    return platform.processor() or None


def _ram_gb() -> float | None:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                return round(kb / 1024 / 1024, 2)
    if platform.system() == "Darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        if out:
            return round(int(out) / 1024**3, 2)
    return None


def _gpu_vram() -> tuple[str | None, float | None]:
    """Discrete GPU name + VRAM in GB. Prefers NVIDIA; falls back to lspci."""
    nv = _run(["nvidia-smi", "--query-gpu=name,memory.total",
               "--format=csv,noheader,nounits"])
    if nv:
        first = nv.splitlines()[0]
        parts = [p.strip() for p in first.split(",")]
        if len(parts) >= 2:
            name = parts[0]
            try:
                vram = round(int(parts[1]) / 1024, 2)  # MiB -> GiB
            except ValueError:
                vram = None
            return name, vram
    lspci = _run(["lspci"])
    if lspci:
        for line in lspci.splitlines():
            if re.search(r"VGA|3D controller", line):
                return line.split(":", 2)[-1].strip(), None
    return None, None


def _vram_tier(vram_gb: float | None) -> int | None:
    """Largest standard tier the machine qualifies for."""
    if vram_gb is None:
        return None
    rounded = round(vram_gb)
    eligible = [t for t in VRAM_TIERS if t <= rounded]
    return eligible[-1] if eligible else None


def _fastfetch() -> str | None:
    """Capture fastfetch output if installed — bonus reference detail."""
    if shutil.which("fastfetch"):
        return _run(["fastfetch", "--logo", "none", "--pipe"])
    return None


def collect() -> dict:
    hostname = socket.gethostname()
    cpu = _cpu_model()
    ram = _ram_gb()
    gpu, vram = _gpu_vram()
    home = Path.home()
    free_gb = round(shutil.disk_usage(home).free / 1024**3, 2)

    info = {
        "hostname": hostname,
        "os": _os_pretty(),
        "kernel": platform.release(),
        "cpu": cpu,
        "cpu_threads": os.cpu_count(),
        "ram_gb": ram,
        "gpu": gpu,
        "vram_gb": vram,
        "vram_tier": _vram_tier(vram),
        "disk_free_gb": free_gb,
    }

    lines = [f"{k:14} {v}" for k, v in info.items()]
    ff = _fastfetch()
    if ff:
        lines += ["", "--- fastfetch ---", ff]
    info["raw_dump"] = "\n".join(lines)
    return info


def upsert(db_path: Path, user_id: int, info: dict) -> int:
    con = sqlite3.connect(db_path)
    try:
        if not con.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone():
            sys.exit(f"error: no user with user_id={user_id} in {db_path}")
        con.execute(
            """
            INSERT INTO user_hardware
                (user_id, hostname, os, kernel, cpu, cpu_threads, ram_gb,
                 gpu, vram_gb, vram_tier, disk_free_gb, raw_dump, collected_at)
            VALUES
                (:user_id, :hostname, :os, :kernel, :cpu, :cpu_threads, :ram_gb,
                 :gpu, :vram_gb, :vram_tier, :disk_free_gb, :raw_dump, datetime('now'))
            ON CONFLICT(user_id, hostname) DO UPDATE SET
                os=excluded.os, kernel=excluded.kernel, cpu=excluded.cpu,
                cpu_threads=excluded.cpu_threads, ram_gb=excluded.ram_gb,
                gpu=excluded.gpu, vram_gb=excluded.vram_gb,
                vram_tier=excluded.vram_tier, disk_free_gb=excluded.disk_free_gb,
                raw_dump=excluded.raw_dump, collected_at=datetime('now')
            """,
            {**info, "user_id": user_id},
        )
        con.commit()
        row = con.execute(
            "SELECT hardware_id FROM user_hardware WHERE user_id=? AND hostname=?",
            (user_id, info["hostname"]),
        ).fetchone()
        return row[0]
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe host hardware into user_hardware.")
    ap.add_argument("--user-id", type=int, default=1, help="owning user_id (default 1)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="path to shell_db.db")
    args = ap.parse_args()

    info = collect()
    hw_id = upsert(args.db, args.user_id, info)

    print(f"user_hardware: row {hw_id} (user_id={args.user_id})")
    for k in ("hostname", "os", "cpu", "cpu_threads", "ram_gb",
              "gpu", "vram_gb", "vram_tier", "disk_free_gb"):
        print(f"  {k:14} {info[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
