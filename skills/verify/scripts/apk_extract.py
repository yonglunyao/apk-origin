#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK data extractor — outputs structured JSON for one APK (or split directory).

Usage:
    python apk_extract.py <apk_or_dir> [--build-tools DIR] [-o out.json]

For Google Play split directories, base + config.* splits are merged
(file inventory + .so/.bundle strings) so the JSON represents the full app.

Requires Android build-tools: apksigner, aapt.
"""
import argparse
import json
import os
import re
import sys
import zipfile
import subprocess
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ── helpers ──────────────────────────────────────────────

def find_build_tools(override):
    if override and Path(override).is_dir():
        return Path(override)
    # 优先：插件内置 build-tools（相对脚本路径向上查找，无需环境变量）
    p = Path(__file__).resolve().parent
    for _ in range(5):
        cand = p / "bin" / "build-tools"
        if cand.is_dir() and ((cand / "aapt.exe").exists() or (cand / "aapt").exists()):
            return cand
        p = p.parent
    env = os.environ.get("ANDROID_BUILD_TOOLS")
    if env and Path(env).is_dir():
        return Path(env)
    for c in [os.path.expanduser("~/AppData/Local/Android/Sdk/build-tools"),
              "/usr/local/lib/android/sdk/build-tools",
              os.environ.get("ANDROID_HOME", "") + "/build-tools",
              os.environ.get("ANDROID_SDK_ROOT", "") + "/build-tools"]:
        c = os.path.expandvars(c)
        if not c.strip() or c == "/build-tools":
            continue
        d = Path(c)
        if d.is_dir():
            subs = sorted([x for x in d.iterdir() if x.is_dir()])
            if subs:
                return subs[-1]
    return None


def tool_path(bt_dir, name):
    if not bt_dir:
        return name
    for cand in (name + ".bat", name + ".exe", name):
        p = bt_dir / cand
        if p.exists():
            return str(p)
    return name


def resolve_apk_set(path):
    """Return (base_apk, [all_apk_paths])."""
    p = Path(path)
    if p.is_file():
        return p, [p]
    apks = sorted(p.glob("*.apk"), key=lambda a: a.stat().st_size, reverse=True)
    if not apks:
        return None, []
    bases = [a for a in apks if "config." not in a.name]
    base = bases[0] if bases else apks[0]
    return base, [base] + [a for a in apks if a != base]


# ── metadata ─────────────────────────────────────────────

BADGING_RE = {
    "label":    r"^application-label:'([^']+)'",
    "package":  r"package: name='([^']+)'",
    "versionName": r"versionName='([^']+)'",
    "versionCode": r"versionCode='([^']+)'",
    "minSdk":   r"sdkVersion:'([^']+)'",
    "targetSdk": r"targetSdkVersion:'([^']+)'",
    "debuggable": r"application-debuggable:'([^']+)'",
    "allowBackup": r"application-allowBackup:'([^']+)'",
}


def get_meta(apk, bt_dir):
    try:
        r = subprocess.run([tool_path(bt_dir, "aapt"), "dump", "badging", str(apk)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return {}
    out = r.stdout or ""
    meta = {}
    for k, pat in BADGING_RE.items():
        m = re.search(pat, out, re.M)
        meta[k] = m.group(1) if m else ""
    meta["permissions"] = sorted(set(
        re.findall(r"uses-permission(?:-sdk-\d+)?:\s*name='([^']+)'", out)))
    return meta


# ── signing certs ────────────────────────────────────────

def get_certs(apk, bt_dir):
    try:
        r = subprocess.run([tool_path(bt_dir, "apksigner"), "verify",
                            "--print-certs", "--verbose", str(apk)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return {"verify_ok": False, "schemes": [], "cert_sha256": "", "cert_dn": ""}
    text = (r.stdout or "") + (r.stderr or "")
    info = {"verify_ok": r.returncode == 0, "schemes": [], "cert_sha256": "", "cert_dn": ""}
    for line in text.splitlines():
        m = re.match(r"\s*Verified using (v[0-9]+).*?:\s*(true|false)", line, re.I)
        if m and m.group(2).lower() == "true":
            info["schemes"].append(m.group(1))
    m = re.search(r"certificate SHA-256 digest:\s*([0-9a-fA-F:]+)", text)
    if m:
        info["cert_sha256"] = m.group(1).lower()
    m = re.search(r"certificate DN:\s*(.+)", text)
    if m:
        info["cert_dn"] = m.group(1).strip()
    return info


# ── manifest components ──────────────────────────────────

def get_components(apk, bt_dir):
    try:
        r = subprocess.run([tool_path(bt_dir, "aapt"), "dump", "xmltree", str(apk),
                            "AndroidManifest.xml"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return {"activity": [], "service": [], "receiver": [], "provider": []}
    out = r.stdout or ""
    comps = {"activity": [], "service": [], "receiver": [], "provider": []}
    current, cur_name, cur_exp = None, "", "false"
    for line in out.splitlines():
        m = re.match(r"\s*E:\s*(\w+)\s", line)
        if m:
            if current and cur_name:
                comps.setdefault(current, []).append([cur_name, cur_exp])
            current = m.group(1) if m.group(1) in comps else None
            cur_name, cur_exp = "", "false"
            continue
        if current:
            nm = re.search(r'android:name\([^)]+\)="([^"]+)"', line)
            if nm:
                cur_name = nm.group(1)
            if 'android:exported' in line:
                cur_exp = "true" if ('0xffffffff' in line or '0x-1' in line) else "false"
    if current and cur_name:
        comps.setdefault(current, []).append([cur_name, cur_exp])
    return comps


# ── file inventory (merged across splits) ────────────────

def scan_files(all_paths):
    libs, dexes, assets, root_files, all_names = [], [], [], [], set()
    for ap in all_paths:
        try:
            z = zipfile.ZipFile(str(ap))
        except Exception:
            continue
        for n in z.namelist():
            all_names.add(n)
            if n.endswith(".so"):
                libs.append(n.split("/")[-1])
            elif re.match(r"^classes\d*\.dex$", n):
                dexes.append(n)
            elif n.startswith("assets/") and not n.endswith("/"):
                assets.append(n)
            elif "/" not in n.rstrip("/"):
                root_files.append(n)
        z.close()
    return {"total": len(all_names),
            "libs": sorted(set(libs)),
            "dex": sorted(set(dexes)),
            "assets": sorted(set(assets)),
            "root_files": sorted(set(root_files))}


# ── string extraction (dex + .so + JS bundles) ───────────

_URL_CHARS = rb"[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%\-]"
URL_RE = re.compile(rb"https?://" + _URL_CHARS + rb"{4,}", re.I)
_STRIP = re.compile(rb"[.,;:'\"!?)>\]}\\\-]+$")
IP_RE = re.compile(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HARMLESS = re.compile(r"(googleapis|gstatic|googleusercontent|flutter\.dev|dart\.dev|"
                      r"w3\.org|w3c|schema|github\.com|schemas\.android\.com|"
                      r"openssl|gnu\.org|kotlinlang|jetbrains|mozilla|apache\.org)", re.I)

# ── sensitive value patterns ───────────────────────────────

_PRINTABLE = re.compile(rb"[\x20-\x7e]{8,}")

_SECRET_PATTERNS = {
    "firebase_api_key":   re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "aws_access_key":     re.compile(rb"AKIA[0-9A-Z]{16}"),
    "jwt_token":          re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "private_key_pem":    re.compile(rb"-----BEGIN\s?(RSA|EC|DSA|PRIVATE|OPENSSH|ENCRYPTED)\s?PRIVATE\s?KEY-----"),
    "google_oauth":       re.compile(rb"[0-9]+-[0-9A-Za-z_-]{25,}\.apps\.googleusercontent\.com"),
    "gcp_service_account": re.compile(rb"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com"),
    "slack_webhook":      re.compile(rb"https://hooks\.slack\.com/services/T[a-z0-9]+/B[a-z0-9]+/[a-z0-9]+"),
    "telegram_bot_token": re.compile(rb"[0-9]+:[A-Za-z0-9_-]{35}"),
    "basic_auth_in_url":  re.compile(rb"https?://[A-Za-z0-9._~-]+:[A-Za-z0-9._~-]+@"),
}

_HARMLESS_SECRET_VALUES = re.compile(
    rb"(example|test|dummy|placeholder|changeme|your-|xxxxxxxx|000000|"
    rb"android\.googlesource\.com|developer\.android\.com|"
    rb"xml\.org|w3\.org|schema\.org)", re.I)


def _extract_printable(data):
    """Extract printable ASCII sequences (>=8 chars) from binary data, one per line."""
    return _PRINTABLE.findall(data)


def _find_secrets(data):
    """Find sensitive values in binary blob. Returns {pattern_name: [matched_string, ...]}."""
    found = {}
    # Strategy: extract printable strings first, then run secret patterns
    # This avoids matching inside binary noise
    strings = _extract_printable(data)
    for name, pattern in _SECRET_PATTERNS.items():
        matches = set()
        for s in strings:
            for m in pattern.finditer(s):
                val = m.group().decode("ascii", "ignore").strip()
                if len(val) >= 8 and not _HARMLESS_SECRET_VALUES.search(m.group()):
                    matches.add(val)
        if matches:
            found[name] = sorted(matches)[:20]
    return found


def extract_strings(all_paths, limit=150):
    urls, ips, so_seen, all_secrets = set(), set(), set(), {}
    for ap in all_paths:
        try:
            z = zipfile.ZipFile(str(ap))
        except Exception:
            continue
        names = z.namelist()
        scan = [n for n in names if re.match(r"^classes\d*\.dex$", n)]
        for n in names:
            if n.endswith(".so"):
                bn = n.split("/")[-1]
                if bn not in so_seen:
                    so_seen.add(bn)
                    scan.append(n)
            elif n.startswith("assets/") and re.search(r"\.(jsbundle|bundle|js|hbc)$", n, re.I):
                scan.append(n)
        for n in scan:
            try:
                data = z.read(n)
            except Exception:
                continue
            for m in URL_RE.finditer(data):
                u = _STRIP.sub(b"", m.group()).decode("ascii", "ignore").lower()
                if len(u) >= 10 and not HARMLESS.search(u):
                    urls.add(u)
            for m in IP_RE.finditer(data):
                ip = m.group().decode()
                segs = [int(x) for x in ip.split(".")]
                if not all(0 <= s <= 255 for s in segs):
                    continue
                if segs[0] in (0, 10, 127, 224, 255):
                    continue
                if segs[0] == 172 and 16 <= segs[1] <= 31:
                    continue
                if segs[0] == 192 and segs[1] == 168:
                    continue
                if all(s < 30 for s in segs):
                    continue
                # filter OID arcs commonly mis-detected as IPs
                if segs[0] == 2 and (segs[1] in (5, 16)):
                    continue  # 2.5.* = id-ce OID, 2.16.* = country OID
                if segs[0] in (80, 115, 101) and segs[1] in (5, 121):
                    continue  # 80.5.*, 115.121.*, 101.3.* = ISO/ITU OID arcs
                if segs[0] == 1 and segs[1] <= 3:
                    continue  # 1.2.*, 1.3.* = ISO/ORG OID arcs
                if segs[0] == 61 and all(s == 1 for s in segs[1:]):
                    continue  # 61.1.1.1 = X.500 OID
                ips.add(ip)
            # ── secret scanning ──
            secrets = _find_secrets(data)
            for k, v in secrets.items():
                all_secrets.setdefault(k, set()).update(v)
        z.close()
    result = {"urls": sorted(urls)[:limit], "ips": sorted(ips)[:limit]}
    if all_secrets:
        result["secrets"] = {k: sorted(v) for k, v in all_secrets.items()}
    return result


# ── main ─────────────────────────────────────────────────

def extract(path, bt_dir):
    base, all_paths = resolve_apk_set(path)
    if base is None:
        return None
    return {
        "apk_path": str(base),
        "meta": get_meta(base, bt_dir),
        "certs": get_certs(base, bt_dir),
        "components": get_components(base, bt_dir),
        "files": scan_files(all_paths),
        "strings": extract_strings(all_paths),
    }


def main():
    ap = argparse.ArgumentParser(description="Extract APK data as JSON")
    ap.add_argument("apk", help=".apk file or split directory")
    ap.add_argument("--build-tools", default=None)
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    bt = find_build_tools(args.build_tools)
    data = extract(args.apk, bt)
    if data is None:
        print("[-] 无法解析 APK 输入", file=sys.stderr)
        sys.exit(1)

    report = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
