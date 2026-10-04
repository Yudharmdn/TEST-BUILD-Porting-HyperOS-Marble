#!/usr/bin/env python3
"""services_sigpatch.py --jar services.jar --baksmali B.jar --smali S.jar --api N --work DIR

Mematikan dua pengecekan signature di services.jar (sama tujuannya dengan toraidl/hyperos_port):
  1. pemanggilan getMinimumSignatureSchemeVersionForTargetSdk di com/android/server/pm/**
     -> hasilnya dipaksa 0
  2. pemanggilan canJoinSharedUserId di ReconcilePackageUtils
     -> hasilnya dipaksa true

PERINGATAN: ini melemahkan keamanan sistem (APK dengan skema signature lama atau
yang bergabung ke sharedUserId yang tidak cocok bisa lolos). Hanya untuk build uji.

Yang diubah hanya instruksi move-result setelah invoke, jadi tanda tangan method
tidak disentuh. Output terakhir: RESULT patched <n_min> <n_join> | RESULT none | RESULT fail <alasan>
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile

MIN_SIG = "getMinimumSignatureSchemeVersionForTargetSdk"
JOIN = "canJoinSharedUserId"


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        raise RuntimeError("%s gagal: %s" % (os.path.basename(cmd[2]) if len(cmd) > 2 else cmd[0], r.stdout[-600:]))
    return r.stdout


def patch_result(text, method, value):
    """Ganti move-result setelah invoke-*->method(...) dengan const/16 <reg>, <value>."""
    pat = re.compile(
        r'(?P<inv>^[ \t]*invoke-[\w/]+ [^\n]*->' + re.escape(method) + r'\([^\n]*\n)'
        r'(?P<gap>(?:[ \t]*(?:\.line [^\n]*)?\n)*)'
        r'(?P<ws>[ \t]*)move-result(?:-\w+)? (?P<reg>[vp]\d+)[ \t]*$',
        re.M,
    )
    return pat.subn(lambda m: "%s%s%sconst/16 %s, %s" % (m.group("inv"), m.group("gap"), m.group("ws"), m.group("reg"), value), text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True)
    ap.add_argument("--baksmali", required=True)
    ap.add_argument("--smali", required=True)
    ap.add_argument("--api", default="34")
    ap.add_argument("--work", required=True)
    a = ap.parse_args()

    shutil.rmtree(a.work, ignore_errors=True)
    os.makedirs(a.work)
    n_min = n_join = 0
    replaced = {}

    with zipfile.ZipFile(a.jar) as zin:
        dex_names = sorted(n for n in zin.namelist() if re.fullmatch(r"classes\d*\.dex", n))
        if not dex_names:
            print("RESULT fail tidak ada classes*.dex di jar")
            return 0
        for dn in dex_names:
            data = zin.read(dn)
            if MIN_SIG.encode() not in data and JOIN.encode() not in data:
                continue
            dexp = os.path.join(a.work, dn)
            with open(dexp, "wb") as fh:
                fh.write(data)
            sdir = os.path.join(a.work, dn[:-4] + "_smali")
            run(["java", "-jar", a.baksmali, "d", "-a", str(a.api), "-o", sdir, dexp])
            changed = 0
            for root, _, files in os.walk(sdir):
                rel = os.path.relpath(root, sdir).replace(os.sep, "/")
                in_pm = rel.startswith("com/android/server/pm")
                for f in files:
                    is_rec = f == "ReconcilePackageUtils.smali"
                    if not f.endswith(".smali") or not (in_pm or is_rec):
                        continue
                    p = os.path.join(root, f)
                    with open(p, encoding="utf-8") as fh:
                        text = fh.read()
                    new = text
                    c1 = c2 = 0
                    if in_pm and MIN_SIG in new:
                        new, c1 = patch_result(new, MIN_SIG, "0x0")
                    if is_rec and JOIN in new:
                        new, c2 = patch_result(new, JOIN, "0x1")
                    if c1 or c2:
                        with open(p, "w", encoding="utf-8") as fh:
                            fh.write(new)
                        n_min += c1
                        n_join += c2
                        changed += c1 + c2
                        print("  %s/%s: min_sig=%d join_shared_uid=%d" % (rel, f, c1, c2))
            if changed:
                out = os.path.join(a.work, dn + ".new")
                run(["java", "-jar", a.smali, "a", "-a", str(a.api), sdir, "-o", out])
                with open(out, "rb") as fh:
                    replaced[dn] = fh.read()

        if not replaced:
            print("RESULT none")
            return 0

        tmp = a.jar + ".patched"
        with zipfile.ZipFile(tmp, "w") as zout:
            for info in zin.infolist():
                payload = replaced.get(info.filename, None)
                if payload is None:
                    payload = zin.read(info)
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.external_attr = info.external_attr
                zi.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(zi, payload)
    os.replace(tmp, a.jar)
    print("RESULT patched %d %d" % (n_min, n_join))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print("RESULT fail %s" % str(e).replace("\n", " ")[:300])
        sys.exit(0)
