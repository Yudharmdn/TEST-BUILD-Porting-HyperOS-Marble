#!/usr/bin/env python3
"""device_features_unlock.py DIR spec [spec ...]

Menyalakan/menambah fitur di semua *.xml pada DIR (product/etc/device_features).
spec = nama:tipe:nilai   (tipe: bool | integer | string)
nilai 'auto' hanya untuk smart_fps_value: diambil dari fps tertinggi di <integer-array name="fpsList">.

Edit dilakukan sebagai teks (regex), bukan lewat parser XML, supaya komentar dan
format file asli tetap utuh. Elemen yang sudah ada diubah nilainya, yang belum ada
ditambahkan sebelum </features>. Bila nama yang sama sudah ada dengan tipe lain, dilewati.
"""
import glob
import os
import re
import sys

TYPES = ("bool", "integer", "string")


def fps_max(text):
    m = re.search(r'<integer-array\s+name="fpsList"\s*>(.*?)</integer-array>', text, re.S)
    if not m:
        return None
    vals = [int(x) for x in re.findall(r'<item>\s*(\d+)\s*</item>', m.group(1))]
    return max(vals) if vals else None


def set_feature(text, name, typ, val):
    """-> (teks_baru, status)"""
    same = re.compile(r'(<%s\s+name="%s"\s*>)(.*?)(</%s>)' % (typ, re.escape(name), typ), re.S)
    m = same.search(text)
    if m:
        if m.group(2).strip() == val:
            return text, "sudah %s" % val
        return same.sub(lambda mm: mm.group(1) + val + mm.group(3), text, count=1), "diubah (%s -> %s)" % (m.group(2).strip(), val)
    if re.search(r'name="%s"' % re.escape(name), text):
        return text, "DILEWATI: nama sudah ada dengan tipe/format lain"
    idx = text.rfind("</features>")
    if idx < 0:
        return text, "DILEWATI: tidak ada </features>"
    line = '    <%s name="%s">%s</%s>\n' % (typ, name, val, typ)
    # sisipkan di awal baris </features>
    start = text.rfind("\n", 0, idx) + 1
    if text[start:idx].strip() == "":
        idx = start
    return text[:idx] + line + text[idx:], "ditambah (%s)" % val


def main():
    if len(sys.argv) < 3:
        print("pemakaian: device_features_unlock.py DIR nama:tipe:nilai ...", file=sys.stderr)
        return 2
    d = sys.argv[1]
    specs = []
    for s in sys.argv[2:]:
        parts = s.split(":", 2)
        if len(parts) != 3 or parts[1] not in TYPES:
            print("spec tidak valid: %s" % s, file=sys.stderr)
            return 2
        specs.append(parts)
    files = sorted(glob.glob(os.path.join(d, "*.xml")))
    if not files:
        print("tidak ada *.xml di %s" % d, file=sys.stderr)
        return 1
    for f in files:
        with open(f, encoding="utf-8", newline="") as fh:
            text = fh.read()
        orig = text
        for name, typ, val in specs:
            if val == "auto":
                v = fps_max(text)
                if v is None:
                    print("%s: %s dilewati (fpsList tidak ada, nilai auto tidak bisa ditentukan)" % (os.path.basename(f), name))
                    continue
                val = str(v)
            text, st = set_feature(text, name, typ, val)
            print("%s: %s -> %s" % (os.path.basename(f), name, st))
        if text != orig:
            with open(f, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
