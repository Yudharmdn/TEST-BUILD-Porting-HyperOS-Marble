#!/usr/bin/env python3
"""
prop_merge.py - salin props khas device dari build.prop base (marble) ke
build.prop port (donor), tanpa menyentuh props identitas/versi build donor.

  prop_merge.py <base.prop> <port.prop> [--dry-run]

Aturan:
- key yang cocok DENY tidak disentuh (versi/fingerprint/build donor, apex, dalvik, ...)
- key lain dari base: ditimpa kalau ada di port dengan nilai berbeda, ditambah kalau belum ada
- baris 'import', komentar dan key yang cuma ada di port dibiarkan
Output: satu baris per perubahan ("~ key: lama -> baru" / "+ key=nilai").
"""
import re
import sys

DENY = [
    r"ro\.build\..*", r"ro\.[a-z_]+\.build\..*", r"ro\.product\.build\..*",
    r"ro\.mi\.os\..*", r"ro\.miui\.ui\.version\..*", r"ro\.miui\.version\..*",
    r"ro\.system\..*", r"ro\.system_ext\..*", r"ro\.com\.google\..*",
    r"ro\.apex\..*", r"dalvik\..*", r"persist\.sys\.dalvik\..*", r"ro\.dalvik\..*",
    r"ro\.boot\..*", r"ro\.adb\..*", r"ro\.debuggable", r"ro\.secure",
    r"ro\.control_privapp_permissions", r"ro\.postinstall\..*",
    r"ro\.product\.(product|system|system_ext|odm)\.(device|name|model|brand|manufacturer|marketname)",
    r"ro\.product\.mod_device", r"ro\.product\.cert", r"ro\.build\.product",
    r"ro\.[a-z_]*\.api_level", r"ro\.product\.first_api_level", r"ro\.vndk\..*",
    r"ro\.zygote.*", r"ro\.surface_flinger\.supports_background_blur",
]
DENY_RE = re.compile("^(" + "|".join(DENY) + ")$")
LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*=(.*)$")


def read_props(path):
    props = {}
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        for line in f:
            m = LINE_RE.match(line.rstrip("\n"))
            if m:
                props[m.group(1)] = m.group(2)
    return props


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    base_path, port_path = sys.argv[1], sys.argv[2]
    dry = "--dry-run" in sys.argv[3:]
    base = read_props(base_path)

    with open(port_path, encoding="utf-8", errors="surrogateescape") as f:
        lines = f.read().split("\n")

    seen = set()
    changes = []
    out = []
    for line in lines:
        m = LINE_RE.match(line)
        if m:
            key, val = m.group(1), m.group(2)
            seen.add(key)
            if key in base and not DENY_RE.match(key) and base[key] != val:
                changes.append("~ %s: %s -> %s" % (key, val, base[key]))
                line = "%s=%s" % (key, base[key])
        out.append(line)

    added = [k for k in base if k not in seen and not DENY_RE.match(k)]
    if added:
        if out and out[-1] == "":
            out.pop()
        out.append("")
        out.append("# ---- props device dari base (prop_merge.py)")
        for k in added:
            out.append("%s=%s" % (k, base[k]))
            changes.append("+ %s=%s" % (k, base[k]))
        out.append("")

    if not dry:
        with open(port_path, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write("\n".join(out))
    for c in changes:
        print(c)


if __name__ == "__main__":
    main()
