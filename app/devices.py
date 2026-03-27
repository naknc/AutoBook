"""Device detection – finds mounted e-readers, MTP devices, and iOS devices."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.logging_utils import log_exception


@dataclass
class ConnectedDevice:
    name: str
    mount_point: str
    kind: str  # "ereader" | "ipad" | "usb" | "mtp"
    status: str = ""  # optional status/hint text
    mtp_storage_id: str = ""  # MTP storage ID for file transfer


_EREADER_NAMES = ("kindle", "kobo", "nook", "pocketbook", "boox", "sony reader")
_EREADER_USB_HINTS = ("kindle", "amazon", "lab126", "kobo", "nook", "pocketbook", "boox")
_AMAZON_VENDOR_ID = "0x1949"
_SKIP_VOLUMES = {"macintosh hd", "macintosh hd - data", "recovery"}


# ── MTP helpers ────────────────────────────────────────────────────

def _has_mtp_tools() -> bool:
    """Check if libmtp CLI tools are available."""
    return shutil.which("mtp-detect") is not None


def _detect_mtp_devices() -> list[ConnectedDevice]:
    """Detect e-readers connected via MTP (used by newer Kindle firmware)."""
    devices: list[ConnectedDevice] = []
    if not _has_mtp_tools():
        return devices
    try:
        out = subprocess.check_output(
            ["mtp-detect"], text=True, stderr=subprocess.STDOUT, timeout=10,
        )
    except Exception:
        log_exception("MTP device detection failed")
        return devices

    # Parse mtp-detect output for device info
    #   "Device 0 (VID=1949 and PID=0004) is a Amazon Kindle 4."
    #   or raw device lines like: "Device#0   VID:PID = 1949:0004"
    for line in out.splitlines():
        line_lower = line.lower()
        if any(hint in line_lower for hint in _EREADER_USB_HINTS):
            # Extract device name from the line
            name = line.strip()
            # Try to clean up common mtp-detect output formats
            if "is a " in line:
                name = line.split("is a ", 1)[1].rstrip(".")
            elif "Device" in line and ":" in line:
                name = line.strip()

            devices.append(ConnectedDevice(
                name=name or "Kindle (MTP)",
                mount_point="",
                kind="mtp",
                status="Connected via MTP. Ready for file transfer.",
            ))
            break  # Usually one e-reader at a time

    # If we found raw devices but no named match, check for Amazon vendor ID
    if not devices and "1949" in out:
        devices.append(ConnectedDevice(
            name="Kindle (MTP)",
            mount_point="",
            kind="mtp",
            status="Connected via MTP. Ready for file transfer.",
        ))

    return devices


def _mtp_send_file(src_path: str, dest_folder: str = "/documents") -> str:
    """Send a file to an MTP device using mtp-sendfile or mtp-connect."""
    src = Path(src_path)

    # Try mtp-sendfile first (simplest)
    if shutil.which("mtp-sendfile"):
        try:
            result = subprocess.run(
                ["mtp-sendfile", str(src), dest_folder + "/" + src.name],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return f"Sent to Kindle via MTP: {dest_folder}/{src.name}"
            # Some versions need different syntax
        except Exception:
            log_exception("mtp-sendfile transfer failed")
            pass

    # Fallback: try mtp-connect with sendfile command
    if shutil.which("mtp-connect"):
        try:
            cmd = f"sendfile {src} {dest_folder}/{src.name}"
            result = subprocess.run(
                ["mtp-connect", "--sendfile", str(src),
                 dest_folder + "/" + src.name],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return f"Sent to Kindle via MTP: {dest_folder}/{src.name}"
        except Exception:
            log_exception("mtp-connect transfer failed")
            pass

    raise RuntimeError(
        "MTP transfer failed. Try:\n"
        "1. Unlock your Kindle\n"
        "2. Disconnect and reconnect the USB cable\n"
        "3. Make sure you're using a data cable (not charge-only)"
    )


# ── macOS detection ────────────────────────────────────────────────

def _detect_macos() -> list[ConnectedDevice]:
    devices: list[ConnectedDevice] = []

    # ── 1. Mounted volumes ─────────────────────────────────────────
    volumes = Path("/Volumes")
    mounted_ereader_found = False
    if volumes.exists():
        for vol in volumes.iterdir():
            if not vol.is_dir() or vol.name.lower() in _SKIP_VOLUMES:
                continue
            is_ereader = (
                any(k in vol.name.lower() for k in _EREADER_NAMES)
                or (vol / "documents").exists()
            )
            kind = "ereader" if is_ereader else "usb"
            if is_ereader:
                mounted_ereader_found = True
            devices.append(ConnectedDevice(vol.name, str(vol), kind))

    # ── 2. USB device scan (system_profiler) ───────────────────────
    usb_devices = _parse_usb_devices()

    for usb_name, usb_info in usb_devices:
        name_lower = usb_name.lower()

        # iPad / iPhone
        if "ipad" in name_lower or "iphone" in name_lower:
            if not any(d.kind == "ipad" for d in devices):
                devices.append(ConnectedDevice(usb_name, "", "ipad"))
            continue

        # E-reader detected via USB
        is_ereader_usb = (
            any(hint in name_lower for hint in _EREADER_USB_HINTS)
            or _AMAZON_VENDOR_ID in usb_info.get("vendor_id", "")
        )
        if is_ereader_usb:
            # Check if already found as a mounted volume
            already_mounted = any(
                d.kind == "ereader"
                and any(hint in d.name.lower() for hint in _EREADER_USB_HINTS)
                for d in devices
            )
            if not already_mounted:
                devices.append(ConnectedDevice(
                    usb_name, "", "ereader",
                    status="Connected via USB but not mounted. "
                           "Unlock your device and check the USB connection.",
                ))

    # ── 3. MTP detection (newer Kindle firmware) ───────────────────
    has_kindle_already = any(
        d.kind in ("ereader", "mtp")
        and ("kindle" in d.name.lower() or "amazon" in d.name.lower())
        for d in devices
    )
    if not has_kindle_already:
        mtp_devices = _detect_mtp_devices()
        devices.extend(mtp_devices)

    # ── 4. ioreg fallback for Amazon Kindle vendor ID ──────────────
    if not any(
        d.kind in ("ereader", "mtp")
        and ("kindle" in d.name.lower() or "amazon" in d.name.lower())
        for d in devices
    ):
        try:
            out = subprocess.check_output(
                ["ioreg", "-p", "IOUSB", "-l", "-w0"],
                text=True, timeout=5,
            )
            if _AMAZON_VENDOR_ID in out.lower() or "kindle" in out.lower():
                devices.append(ConnectedDevice(
                    "Kindle (USB detected)", "", "ereader",
                    status="Kindle detected on USB bus but not mounted. "
                           "Try a different cable or unlock the Kindle.",
                ))
        except Exception:
            log_exception("macOS ioreg Kindle detection failed")

    # ── 5. ifuse-mounted iPad ──────────────────────────────────────
    ipad_mount = Path.home() / "ipad_mount"
    if ipad_mount.exists() and any(ipad_mount.iterdir()) \
       and not any(d.kind == "ipad" for d in devices):
        devices.append(ConnectedDevice("iPad (ifuse)", str(ipad_mount), "ipad"))

    return devices


def _parse_usb_devices() -> list[tuple[str, dict[str, str]]]:
    """Parse system_profiler SPUSBDataType, return [(name, {key: value}), …]."""
    result: list[tuple[str, dict[str, str]]] = []
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPUSBDataType", "-detailLevel", "mini"],
            text=True, timeout=5,
        )
    except Exception:
        log_exception("system_profiler USB parse failed")
        return result

    current_name = ""
    current_info: dict[str, str] = {}
    for line in out.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Device name lines are indented and end with ':'
        # but don't start with known key prefixes
        if stripped.endswith(":") and ":" not in stripped[:-1]:
            if current_name:
                result.append((current_name, current_info))
            current_name = stripped.rstrip(":").strip()
            current_info = {}
        elif current_name and ":" in stripped:
            key, _, val = stripped.partition(":")
            current_info[key.strip().lower().replace(" ", "_")] = val.strip()

    if current_name:
        result.append((current_name, current_info))

    return result


# ── Linux detection ────────────────────────────────────────────────

def _detect_linux() -> list[ConnectedDevice]:
    devices: list[ConnectedDevice] = []
    user = os.getenv("USER", "")
    media = Path(f"/media/{user}") if user else Path("/media")
    if media.exists():
        for vol in media.iterdir():
            if vol.is_dir():
                kind = "ereader" if any(k in vol.name.lower() for k in ("kindle", "kobo")) else "usb"
                devices.append(ConnectedDevice(vol.name, str(vol), kind))

    # MTP fallback on Linux too
    if not any(d.kind in ("ereader", "mtp") for d in devices):
        mtp_devices = _detect_mtp_devices()
        devices.extend(mtp_devices)

    return devices


# ── Public API ─────────────────────────────────────────────────────

def detect_devices() -> list[ConnectedDevice]:
    """Return connected e-reader / tablet devices."""
    return {"Darwin": _detect_macos, "Linux": _detect_linux}.get(
        platform.system(), lambda: []
    )()


def copy_to_device(src_path: str, device: ConnectedDevice, subdir: str = "") -> str:
    """Copy a book file to the device. Returns destination path or status message."""
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"Source file not found: {src_path}")

    # MTP device – use libmtp tools
    if device.kind == "mtp":
        target = "/documents"
        if subdir.strip():
            target = f"{target}/{subdir.strip().strip('/')}"
        return _mtp_send_file(src_path, target)

    if device.kind == "ipad" and not device.mount_point:
        if platform.system() != "Darwin":
            raise RuntimeError(f"'{device.name}' is not mountable. Use ifuse or transfer manually.")
        try:
            subprocess.Popen(["open", "-a", "Books", str(src)])
            return f"Opened in Books app – sync to {device.name} via Finder/iCloud"
        except Exception:
            subprocess.Popen(["open", str(src)])
            return f"Opened file – use Share to send to {device.name}"

    if not device.mount_point:
        raise RuntimeError(f"'{device.name}' has no mount point.")

    dest_dir = Path(device.mount_point)
    if not dest_dir.exists():
        raise RuntimeError(f"Mount point '{device.mount_point}' does not exist.")

    if device.kind == "ereader":
        docs = dest_dir / "documents"
        if docs.exists():
            dest_dir = docs
    if subdir.strip():
        dest_dir = dest_dir / subdir.strip().strip("/")
        dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / src.name
    shutil.copy2(str(src), str(dest))
    return str(dest)
