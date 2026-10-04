#!/usr/bin/env bash
# =============================================================================
#  port_extras.sh - tambahan untuk scripts/port.sh (di-source, hanya berisi fungsi)
#
#  Memakai helper dan variabel dari port.sh:
#    log ok warn die is_true get_prop set_prop
#    P_FS B_FS TOOLS_DIR WORK SCRIPT_DIR
#
#  Fungsi:
#    fix_aod_overlay            DevicesAndroidOverlay -> DozeService milik SystemUI (kalau donor tak punya com.miui.aod)
#    millet_fix                 ro.millet.netlink disamakan dengan marble
#    unlock_device_features     nyalakan fitur tambahan di product/etc/device_features/*.xml
#    patch_services_signature   (opsional, default MATI) matikan cek signature di services.jar
# =============================================================================

AOD_FIX=${AOD_FIX:-auto}            # auto | true | false
MILLET_FIX=${MILLET_FIX:-true}
# UNLOCK_FEATURES (default dan format) dideklarasikan di blok konfigurasi port.sh.
SIGNATURE_PATCH=${SIGNATURE_PATCH:-false}   # true = patch services.jar (melemahkan keamanan, hanya build uji)

# ------------------------------------------------------------------ helper APK
# apk_tool d|b <input> <output>  (apktool dari toolkit, lalu apktool di PATH, lalu APKEditor.jar)
apk_tool() {
    local mode=$1 in=$2 out=$3 at="$TOOLS_DIR/bin/apktool"
    if [[ -f $at/apktool ]]; then
        chmod +x "$at/apktool" 2>/dev/null || true
        "$at/apktool" "$mode" "$in" -o "$out" -f > "$WORK/apktool.log" 2>&1
    elif command -v apktool >/dev/null; then
        apktool "$mode" "$in" -o "$out" -f > "$WORK/apktool.log" 2>&1
    elif [[ -f $at/APKEditor.jar ]]; then
        java -jar "$at/APKEditor.jar" "$mode" -i "$in" -o "$out" -f > "$WORK/apktool.log" 2>&1
    else
        echo "apktool/APKEditor tidak ditemukan di $at maupun PATH" > "$WORK/apktool.log"
        return 127
    fi
}

# apk_sign <apk>: zipalign + tanda tangan kunci uji (in-place). Overlay di /product tidak
# butuh tanda tangan yang sama dengan target, tapi APK tanpa tanda tangan bisa ditolak PackageManager.
apk_sign() {
    local apk=$1 ks="$WORK/port_test.jks"
    if ! command -v apksigner >/dev/null; then
        warn "sign: apksigner tidak ada, $(basename "$apk") tidak ditandatangani (kalau bootloop, cek ini dan SIGNATURE_PATCH)"
        return 0
    fi
    if command -v zipalign >/dev/null; then
        zipalign -f -p 4 "$apk" "$apk.al" && mv -f "$apk.al" "$apk" || true
    fi
    if [[ ! -f $ks ]]; then
        keytool -genkeypair -keystore "$ks" -storepass android -keypass android -alias port \
            -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=port" >/dev/null 2>&1 \
            || { warn "sign: keytool gagal membuat kunci uji"; return 0; }
    fi
    if apksigner sign --ks "$ks" --ks-pass pass:android --key-pass pass:android "$apk" >/dev/null 2>&1; then
        ok "sign: $(basename "$apk") ditandatangani (kunci uji)"
    else
        warn "sign: apksigner gagal untuk $(basename "$apk")"
    fi
}

# ------------------------------------------------------------------ AOD
# DevicesAndroidOverlay dari marble menunjuk ke com.miui.aod/...DozeService. Kalau ROM donor
# tidak membawa com.miui.aod, komponen itu tidak ada -> AOD/doze rusak. Toraidl mengganti
# ke DozeService milik SystemUI. Mode auto: hanya patch bila perlu.
fix_aod_overlay() {
    local apk pkgs dec out n=0 f
    if [[ $AOD_FIX == false ]]; then log "AOD: dimatikan (AOD_FIX=false)"; return 0; fi
    apk=$(find "$P_FS/product" -type f -name DevicesAndroidOverlay.apk 2>/dev/null | head -n1 || true)
    if [[ -z $apk ]]; then log "AOD: DevicesAndroidOverlay.apk tidak ada di port, dilewati"; return 0; fi

    if ! python3 - "$apk" 2>/dev/null <<'PY'
import sys, zipfile
needle = "com.miui.aod.doze.DozeService"
data = zipfile.ZipFile(sys.argv[1]).read("resources.arsc")
sys.exit(0 if needle.encode() in data or needle.encode("utf-16-le") in data else 1)
PY
    then
        log "AOD: overlay tidak merujuk com.miui.aod DozeService, tidak perlu patch"
        return 0
    fi

    if [[ $AOD_FIX == auto ]]; then
        pkgs=$(python3 "$SCRIPT_DIR/apk_index.py" "$P_FS" | cut -f1 || true)
        if grep -qx 'com.miui.aod' <<< "$pkgs"; then
            ok "AOD: donor punya com.miui.aod, overlay marble dipakai apa adanya (AOD_FIX=true untuk memaksa patch)"
            return 0
        fi
        log "AOD: donor tidak punya com.miui.aod -> overlay diarahkan ke DozeService SystemUI"
    fi

    dec="$WORK/aod_overlay"; out="$WORK/DevicesAndroidOverlay.patched.apk"
    rm -rf "$dec" "$out"
    if ! apk_tool d "$apk" "$dec"; then
        tail -n 15 "$WORK/apktool.log" >&2
        warn "AOD: decode overlay gagal, overlay marble dipertahankan"; return 0
    fi
    while IFS= read -r f; do
        sed -i 's|com\.miui\.aod/com\.miui\.aod\.doze\.DozeService|com.android.systemui/com.android.systemui.doze.DozeService|g' "$f"
        n=$((n + 1))
    done < <(grep -rlF 'com.miui.aod.doze.DozeService' "$dec" --include='*.xml' 2>/dev/null || true)
    if [[ $n -eq 0 ]]; then
        warn "AOD: string DozeService tidak ditemukan di XML hasil decode, overlay dipertahankan"; return 0
    fi
    if ! apk_tool b "$dec" "$out"; then
        tail -n 15 "$WORK/apktool.log" >&2
        warn "AOD: build ulang overlay gagal, overlay marble dipertahankan"; return 0
    fi
    apk_sign "$out"
    cp -f "$out" "$apk"
    ok "AOD: $(basename "$apk") dipatch ($n file XML), DozeService -> com.android.systemui"
}

# ------------------------------------------------------------------ Millet
# ro.millet.netlink = nomor netlink yang didaftarkan kernel untuk Millet (pembekuan app).
# Harus sama dengan kernel yang dipakai. Disamakan dengan marble, dan dibuang dari partisi
# donor lain supaya tidak ada yang menimpa (urutan load: system -> system_ext -> vendor -> odm -> product -> mi_ext).
millet_fix() {
    local key=ro.millet.netlink val="" src="" f old
    is_true "$MILLET_FIX" || { log "Millet: dimatikan (MILLET_FIX=false)"; return 0; }
    for f in "$B_FS/product/etc/build.prop" "$B_FS/vendor/build.prop" "$B_FS"/odm/etc/*build.prop; do
        [[ -f $f ]] || continue
        val=$(get_prop "$f" "$key")
        if [[ -n $val ]]; then src=${f#"$B_FS"/}; break; fi
    done
    if [[ -z $val ]]; then
        warn "Millet: $key tidak ditemukan di base marble (product/vendor/odm), nilai donor tidak diubah"
        return 0
    fi
    old=$(cat "$P_FS/system/system/build.prop" "$P_FS/system_ext/etc/build.prop" \
              "$P_FS/product/etc/build.prop" "$P_FS/mi_ext/etc/build.prop" 2>/dev/null \
          | sed -n "s/^${key//./\\.}=//p" | tail -n1 || true)
    for f in "$P_FS/system/system/build.prop" "$P_FS/system_ext/etc/build.prop" "$P_FS/mi_ext/etc/build.prop"; do
        if [[ -f $f ]]; then sed -i "/^${key//./\\.}=/d" "$f"; fi
    done
    set_prop "$P_FS/product/etc/build.prop" "$key" "$val"
    ok "Millet: $key = $val (dari base $src; donor: ${old:-kosong})"
    log "Millet: kalau memakai BOOT_IMG kernel custom, nilai ini harus sama dengan netlink yang didaftarkan kernel tersebut"
}

# ------------------------------------------------------------------ device_features
unlock_device_features() {
    local d="$P_FS/product/etc/device_features" out
    local feats=${UNLOCK_FEATURES:-}
    case ${feats,,} in
        ""|none|off|false) log "device_features: UNLOCK_FEATURES=${feats:-kosong}, dilewati"; return 0 ;;
    esac
    if [[ ! -d $d ]]; then warn "device_features: $d tidak ada, dilewati"; return 0; fi
    # shellcheck disable=SC2086  # daftar spec sengaja di-split
    if ! out=$(python3 "$SCRIPT_DIR/device_features_unlock.py" "$d" $feats 2>&1); then
        printf '    %s\n' "$out" >&2
        warn "device_features: unlock gagal, file dibiarkan seperti semula"
        return 0
    fi
    while IFS= read -r f; do printf '    %s\n' "$f"; done <<< "$out"
    ok "device_features: unlock selesai (UNLOCK_FEATURES)"
}

# ------------------------------------------------------------------ signature services.jar
patch_services_signature() {
    local jar bj sj api res line
    if ! is_true "$SIGNATURE_PATCH"; then
        log "signature: patch services.jar dimatikan (SIGNATURE_PATCH=false, default)"
        return 0
    fi
    warn "signature: SIGNATURE_PATCH=true melemahkan verifikasi signature (skema lama & sharedUserId). Hanya untuk build uji"
    jar=$(find "$P_FS/system/system/framework" -maxdepth 1 -type f -name services.jar 2>/dev/null | head -n1 || true)
    bj=$(find "$TOOLS_DIR/bin/apktool" -maxdepth 1 -name 'baksmali-*.jar' 2>/dev/null | sort | tail -n1 || true)
    sj=$(find "$TOOLS_DIR/bin/apktool" -maxdepth 1 -name 'smali-*.jar' 2>/dev/null | sort | tail -n1 || true)
    if [[ -z $jar ]]; then warn "signature: services.jar tidak ditemukan, dilewati"; return 0; fi
    if ! command -v java >/dev/null || [[ -z $bj || -z $sj ]]; then
        warn "signature: java / baksmali / smali tidak tersedia, services.jar tidak dipatch"; return 0
    fi
    api=$(get_prop "$P_FS/system/system/build.prop" ro.build.version.sdk)
    python3 "$SCRIPT_DIR/services_sigpatch.py" --jar "$jar" --baksmali "$bj" --smali "$sj" \
        --api "${api:-34}" --work "$WORK/sigpatch" > "$WORK/sigpatch.log" 2>&1 || true
    while IFS= read -r line; do
        case $line in RESULT*|*JAVA_TOOL_OPTIONS*) ;; *) printf '    %s\n' "$line" ;; esac
    done < "$WORK/sigpatch.log"
    res=$(sed -n 's/^RESULT //p' "$WORK/sigpatch.log" | tail -n1)
    case $res in
        patched*) ok "signature: services.jar dipatch (${res#patched } = min_sig join_shared_uid)" ;;
        none*)    warn "signature: nama method tidak ditemukan di services.jar donor (mungkin berganti nama di Android ini), tidak ada yang diubah" ;;
        *)        warn "signature: patch gagal (${res:-tanpa hasil}), services.jar tidak diubah, lihat $WORK/sigpatch.log" ;;
    esac
    rm -rf "$WORK/sigpatch"
}
