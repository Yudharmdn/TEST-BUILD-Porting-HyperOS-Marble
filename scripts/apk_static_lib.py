#!/usr/bin/env python3
"""apk_static_lib.py <apk>

Cetak info static shared library dari AndroidManifest.xml (biner) sebuah APK, satu baris per entri:

    provides <nama-library> <versi>     (elemen <static-library>)
    uses     <nama-library> <versi>     (elemen <uses-static-library>)

Dipakai port_chrome.sh: Chrome (Trichrome) memakai com.google.android.trichromelibrary dengan
versi TEPAT sama dengan yang disediakan TrichromeLibrary di ROM. Kalau beda, Chrome tidak ter-install.
"""
import struct
import sys
import zipfile

RES_STRING_POOL = 0x0001
RES_XML_START_ELEMENT = 0x0102
UTF8_FLAG = 0x100
NONE = 0xFFFFFFFF
TYPE_STRING = 0x03


def _strings(buf, off):
    (_t, hsize, _size, count, _style, flags, str_start, _sty_start) = struct.unpack_from("<HHIIIIII", buf, off)
    offsets = struct.unpack_from("<%dI" % count, buf, off + hsize)
    base = off + str_start
    utf8 = bool(flags & UTF8_FLAG)
    out = []
    for o in offsets:
        p = base + o
        if utf8:
            n = buf[p]; p += 1
            if n & 0x80:
                p += 1
            ln = buf[p]; p += 1
            if ln & 0x80:
                ln = ((ln & 0x7F) << 8) | buf[p]; p += 1
            out.append(buf[p:p + ln].decode("utf-8", "replace"))
        else:
            ln = struct.unpack_from("<H", buf, p)[0]; p += 2
            if ln & 0x8000:
                ln = ((ln & 0x7FFF) << 16) | struct.unpack_from("<H", buf, p)[0]; p += 2
            out.append(buf[p:p + ln * 2].decode("utf-16-le", "replace"))
    return out


def static_libs(data):
    """-> [(provides|uses, nama, versi)]"""
    if len(data) < 8:
        return []
    _t, hsize, _size = struct.unpack_from("<HHI", data, 0)
    pos = hsize
    strings = []
    res = []
    while pos + 8 <= len(data):
        ctype, _chsize, csize = struct.unpack_from("<HHI", data, pos)
        if csize < 8:
            break
        if ctype == RES_STRING_POOL:
            strings = _strings(data, pos)
        elif ctype == RES_XML_START_ELEMENT:
            name_idx = struct.unpack_from("<I", data, pos + 20)[0]
            ename = strings[name_idx] if name_idx < len(strings) else ""
            if ename in ("static-library", "uses-static-library"):
                a_start, a_size, a_count = struct.unpack_from("<HHH", data, pos + 24)
                ap = pos + 16 + a_start
                attrs = {}
                for i in range(a_count):
                    base = ap + i * a_size
                    _ns, an, raw = struct.unpack_from("<III", data, base)
                    _sz, _r0, dtype, dval = struct.unpack_from("<HBBI", data, base + 12)
                    key = strings[an] if an < len(strings) else ""
                    if raw != NONE and raw < len(strings):
                        val = strings[raw]
                    elif dtype == TYPE_STRING and dval < len(strings):
                        val = strings[dval]
                    else:
                        val = dval
                    attrs[key] = val
                if "name" in attrs:
                    kind = "provides" if ename == "static-library" else "uses"
                    res.append((kind, attrs["name"], attrs.get("version", 0)))
        pos += csize
    return res


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    try:
        with zipfile.ZipFile(sys.argv[1]) as z:
            data = z.read("AndroidManifest.xml")
    except Exception:
        return
    for kind, name, ver in static_libs(data):
        print("%s %s %s" % (kind, name, ver))


if __name__ == "__main__":
    main()
