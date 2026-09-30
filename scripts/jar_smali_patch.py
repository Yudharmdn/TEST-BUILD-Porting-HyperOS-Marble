#!/usr/bin/env python3
"""
jar_smali_patch.py - kosongkan constructor sebuah class di dalam .jar framework
(dipakai untuk SystemServerImpl di miui-services.jar ROM xiaomi.eu, sama seperti
toraidl/hyperos_port: constructor diganti hanya memanggil constructor superclass).

  jar_smali_patch.py --jar miui-services.jar --cls com/android/server/SystemServerImpl
                     --baksmali baksmali.jar --smali smali.jar --api 36 --work DIR

Output (stdout): isi constructor asli (untuk log), lalu "RESULT patched|already|notfound|error <pesan>".
Exit code 0 selalu; pemanggil membaca baris RESULT.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile

CTOR_RE = re.compile(r"^\.method public constructor <init>\(\)V\n.*?^\.end method\n?", re.M | re.S)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--cls", required=True)
    ap.add_argument("--baksmali", required=True)
    ap.add_argument("--smali", required=True)
    ap.add_argument("--api", default="34")
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    # smali/baksmali 3.0.5 hanya kenal API <= 34 (API 35/36 -> "dexVersion must be within [0, 999]").
    # API 34 = dex 039, tetap dibaca ART Android 15/16/17; opcode sama.
    try:
        a.api = str(min(int(a.api), 34))
    except ValueError:
        a.api = "34"

    shutil.rmtree(a.work, ignore_errors=True)
    os.makedirs(a.work)
    with zipfile.ZipFile(a.jar) as z:
        dexes = sorted(n for n in z.namelist() if re.fullmatch(r"classes\d*\.dex", n))
        for n in dexes:
            with open(os.path.join(a.work, n), "wb") as f:
                f.write(z.read(n))
    if not dexes:
        print("RESULT error jar tanpa classes*.dex")
        return 0

    target_dex = target_smali = out_dir = None
    for n in dexes:
        d = os.path.join(a.work, n[:-4])
        rc, out = run(["java", "-jar", a.baksmali, "d", "--api", a.api, os.path.join(a.work, n), "-o", d])
        if rc != 0:
            print("RESULT error baksmali %s gagal: %s" % (n, out.splitlines()[-1] if out else rc))
            return 0
        p = os.path.join(d, a.cls + ".smali")
        if os.path.isfile(p):
            target_dex, target_smali, out_dir = n, p, d
            break
    if not target_smali:
        print("RESULT notfound %s tidak ada di %s" % (a.cls, os.path.basename(a.jar)))
        return 0

    src = open(target_smali, encoding="utf-8").read()
    m = CTOR_RE.search(src)
    sup = re.search(r"^\.super (L[^;]+;)", src, re.M)
    if not m or not sup:
        print("RESULT notfound constructor <init>()V / .super tidak ditemukan")
        return 0
    body = m.group(0)
    new = (".method public constructor <init>()V\n    .registers 1\n\n"
           "    invoke-direct {p0}, %s-><init>()V\n\n    return-void\n.end method\n" % sup.group(1))
    code_lines = [l for l in body.splitlines()[1:-1] if l.strip() and not l.strip().startswith((".registers", ".locals", ".line", ".prologue", "#"))]
    if len(code_lines) <= 2:
        print("RESULT already constructor sudah minimal")
        return 0
    print("constructor asli (%d baris instruksi):" % len(code_lines))
    for l in code_lines:
        print("  " + l.strip())
    open(target_smali, "w", encoding="utf-8").write(src[:m.start()] + new + src[m.end():])

    new_dex = os.path.join(a.work, "new_" + target_dex)
    rc, out = run(["java", "-jar", a.smali, "a", "--api", a.api, out_dir, "-o", new_dex])
    if rc != 0:
        print("RESULT error smali gagal: %s" % (out.splitlines()[-1] if out else rc))
        return 0

    tmp_jar = os.path.join(a.work, "patched.jar")
    with zipfile.ZipFile(a.jar) as zin, zipfile.ZipFile(tmp_jar, "w") as zout:
        for info in zin.infolist():
            data = open(new_dex, "rb").read() if info.filename == target_dex else zin.read(info.filename)
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)
    shutil.copyfile(tmp_jar, a.jar)
    print("RESULT patched %s (%s)" % (a.cls.replace("/", "."), target_dex))
    return 0


if __name__ == "__main__":
    sys.exit(main())
