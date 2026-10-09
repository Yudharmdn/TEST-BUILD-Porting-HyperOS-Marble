# HyperOS Port for POCO F5 (marble)

This repo is a GitHub Actions workflow that quick-ports HyperOS from other Xiaomi phones to the POCO F5 (marble). Everything runs on GitHub's runners, so you don't need a beefy PC or a Linux box at home. You paste the ROM links, hit Run, wait about 20 minutes, and download the zip.

The output is a zip you can install straight from OrangeFox. Its contents and layout follow the xiaomi.eu ROM on purpose.

> **This is still a TEST build.** The workflow runs and the zip gets built, but porting across Android versions always carries a risk of bootloops or broken features. Back up anything important first, and make sure you know how to get back to your previous ROM.

## How it works

In short, the ported ROM is put together from two ROMs:

- **Base (marble):** the xiaomi.eu marble ROM. Everything tied to the hardware comes from here: firmware, `vendor`, `odm`, `vendor_dlkm`, `vendor_boot`, `dtbo`.
- **Donor:** HyperOS from another phone, e.g. the REDMI K90 (annibale) on Android 17. The UI and the system come from here: `system`, `system_ext`, `product`, `mi_ext`.

After merging them, `scripts/port.sh` patches the parts that usually stop a port from booting:

- **Props:** build.prop is adjusted for marble (codename, model, density, and the audio/bluetooth/etc. props from the base).
- **Device files:** `device_features`, `displayconfig`, the device overlays and MiuiCamera are taken from marble, not the donor. The camera's privileged-permission allowlist from marble is copied along with it, otherwise system_server can refuse to boot.
- **More pieces from marble** (the same list [toraidl/hyperos_port](https://github.com/toraidl/hyperos_port) uses): the framework, MIUI framework, Settings, biometric and telephony overlays, which carry the brightness range, camera cutout, rounded corners and fingerprint sensor position, plus MiSound (audio effects tied to the vendor Dolby HAL) and the face unlock app.
- **Updater removed:** the donor's updater app would offer OTAs built for another phone, and installing one on marble can brick it.
- **From [HyperOS-Port-Python](https://github.com/toraidl/HyperOS-Port-Python):** the carrier config and SystemUI device overlays, bootanimation, and on an Android 15 base with a HyperOS 3 donor, marble's VoiceTrigger (the donor one crashes there). `ro.miui.density.primaryscale` is dropped and `ro.miui.cust_erofs` is set. If the overlay still points AOD at `com.miui.aod`, it is redirected to the doze service in the donor's SystemUI.
- **xiaomi.eu donors:** like toraidl, the constructor of `SystemServerImpl` in `miui-services.jar` is emptied so it only calls its parent class, and `device_info.json` comes from marble. The original constructor is printed in the build log so you can see what was removed.
- **VINTF:** the marble vendor is FCM level 6 (Android 12), which Android 17 no longer knows about. The script copies `compatibility_matrix.6.xml` from the base system into `/system/etc/vintf/` of the port (that's the framework side, the VINTF files in `/vendor` and `/odm` are left untouched). It also checks the other direction, making sure everything the vendor's matrix asks for is provided by the framework.
- **VNDK:** the VNDK v32 APEX is copied from the base into `/system_ext/apex`, and `vendor-ndk 32` is declared in a framework manifest fragment, since newer Android donors don't ship either anymore.
- **Linker:** every library the vendor/odm binaries need is checked one by one, and the result shows up in the log.
- **64-bit-only donors:** if the donor ships no 32-bit libs (`ARCH64_FIX=auto` checks `system/lib` and the ABI list), the 64-bit port guide is applied on top of the marble 64-32 vendor: `linker`/`linker_asan` and `vold` from the base, odm/vendor ABI + zygote props, media omx rc/HAL removed, mediaserver import fixed. Donors that are still 64-32 are left alone. Untested on real hardware.
- **fstab and vbmeta:** `/data` encryption is removed (in `vendor/etc/fstab.qcom` and in the first-stage fstab inside `vendor_boot`), the partitions in `ext4_partitions` are mounted rw, and verity is disabled in `vbmeta` and `vbmeta_system`.
- **Keyboard:** Gboard is added as a system app, and the Chinese keyboards (Sogou, Baidu, iFlytek) are removed. With no other keyboard left, Gboard becomes the default on its own.
- **Google apps from the base:** if the donor has no Play Services, GSF or Play Store (typical for China ROMs), they are copied from the base ROM's product partition (`GMS_FROM_BASE=auto`, `GMS_SCOPE=core`). If the donor already has them, nothing is copied.
- **device_features unlock:** a few extra features are switched on in `marble.xml` and `marblein.xml` (smart FPS at the highest refresh rate, default eye-care mode, AOD fullscreen/always-on). Use the `unlock_features` input to change the list, or `none` to turn it off.
- **Debloat:** unneeded apps are removed based on `debloat_packages.txt`.
- **boot.img:** the workflow sets `BOOT_IMG` to the custom Melt-Rebase kernel (`Yudharmdn/boot-melt-rebase`), so that kernel replaces the base `boot.img`. Set `BOOT_IMG: ""` in `.github/workflows/port-hyperos.yml` to use the stock marble kernel from the base ROM instead, which is the safest choice for a first flash. The build checks that a custom boot.img still has a ramdisk (marble has no init_boot, so first-stage init lives there) and that the kernel is the same 5.10 series as the base. The modules in `vendor_boot` and `vendor_dlkm` are built for the base kernel, so if only the sublevel differs (for example 5.10.236 vs 5.10.270) the build just prints a warning. If the screen or touch is dead after boot, look for `disagrees about version` or `version magic` in `dmesg`.

## What's inside the zip

```
META-INF/                 installer from xiaomi.eu
images/abl.img ... xbl_ramdump.img   marble firmware
images/boot.img           kernel (custom from BOOT_IMG, stock marble if BOOT_IMG is empty)
images/vendor_boot.img    patched (fstab)
images/dtbo.img
images/vbmeta.img, vbmeta_system.img
images/cust.img
images/super.img.0 ... super.img.8   super partition split into 9 chunks
```

A few things are done this way on purpose:

- **recovery.img is not included**, so the OrangeFox on your phone stays untouched.
- **The installer only flashes.** Any format or wipe command in META-INF is neutralized during the build, and if one somehow slips through, the build fails on purpose.

## Building

1. Fork or clone this repo.
2. Open the **Actions** tab, pick **Port HyperOS -> marble (Recovery)**, and click **Run workflow**.
3. Fill in the inputs:

| Input | What to put there |
|---|---|
| `base_rom_url` | link to the xiaomi.eu marble zip (sourceforge). It has to be the recovery zip, since its META-INF is reused as the installer |
| `port_rom_url` | link to the donor's full OTA zip (the one with `payload.bin` inside) |
| `super_size` | `9663676416` (marble's super size, leave it as is) |
| `ext4_partitions` | default `system system_ext product mi_ext vendor odm vendor_dlkm`: every partition is EXT4 and can be edited directly on the phone. Anything not listed becomes EROFS (read-only). With all seven as EXT4 the super partition is almost full (about 99%); if a donor does not fit, the build fails with a message instead of silently switching to EROFS |
| `debloat` | extra paths to remove, space separated. Can be left empty |
| `unlock_features` | extra `device_features` entries as `name:type:value`, space separated. Empty = script defaults, `none` = turn off |
| `disable_encryption` | leave it `true` |
| `rw_mount` | leave it `true` |
| `debug_adb` | `true` by default. adb is on from boot (`ro.adb.secure=0`, debuggable), handy for logcat. This is a debug build, so turn it off once things are stable and before sharing the zip |
| `recovery_img_url` | leave it empty |
| `release_repo` | empty = output goes to Artifacts. Set it to `owner/repo` to upload to a Release instead (needs the `RELEASE_TOKEN` secret) |

4. Wait for it to finish, then grab the zip from the **Artifacts** section of the run page. The zip is kept for 90 days. If the build fails, the working logs are uploaded as a separate artifact for 7 days.

If the build fails, open the **Port ROM** step in the log. Every stage has a header (0/7 through 7/7), and the `[warn]` or `[fail]` lines usually point right at the problem.

### Does it work with an Android 16 donor?

Yes. The script isn't tied to Android 17. All the checks (VINTF, VNDK, linker) adapt to whatever is in the donor ROM.

## Flashing

1. Boot into OrangeFox.
2. Install the zip.
3. **Format Data** (Wipe → Format Data → type `yes`). This is required on a first install, because encryption is disabled and the Android version is different. Skip it and you will almost certainly bootloop.
4. Reboot to System. The first boot takes a while, up to 10 minutes, so be patient.

Updating later to a newer build made with the same settings usually doesn't need another format.

## After installing, keep in mind

Some apps are removed through `debloat_packages.txt`, so a few things are on you:

- **Browser:** there is none. Xiaomi's browser is on the debloat list and the donor ROMs used so far don't ship Chrome. Have a Chrome or other browser APK ready.
- **Google apps:** whatever the donor ships stays. xiaomi.eu donors come with Play Store and Play Services, official Chinese OTAs usually don't. The build log lists them under `Google:`.
- **NFC:** not removed. Nothing in `debloat_packages.txt` touches it. If you want it gone, add the NFC app to that list.
- **Other things that are gone:** Print, SIM Toolkit, the QR Scanner, Find Device, Joyose (game profiles), the Downloads app UI (the download provider stays), Notes, Music, Sound Recorder, Compass, Health and Mi Share. `debloat_packages.txt` is the full list, and the build log shows what was actually removed.

## Tweaking the debloat list

Everything lives in `debloat_packages.txt`, and the format is relaxed:

```
com.miui.notes                 # remove by package name
MiuiCompass                    # or by APK folder name
product/app/SogouIME           # or by full path
!product/priv-app/MiuiCamera   # a leading ! means never remove this
```

A couple of rules:

- **Missing packages:** anything that isn't in the ROM is just skipped, and the build doesn't fail.
- **Important apps:** SystemUI, Settings, the launcher, Security, GMS, WebView and similar are protected by the script, so even if one ends up on the list by accident it won't be removed.

## marble-specific files

The `devices/marble/` folder holds files that get copied over the ROM before it's packed, so it keeps matching the marble hardware:

```
devices/marble/product/etc/device_features/   marble.xml, marblein.xml
devices/marble/product/etc/displayconfig/     display & brightness config
devices/marble/product/overlay/               DevicesOverlay.apk, DevicesAndroidOverlay.apk,
                                              AospFrameworkResOverlay.apk, MiuiFrameworkResOverlay.apk
```

These are copied after the files taken straight from the base ROM, so when the same file exists in both places, the one in this folder wins. If there's anything else you want forced to the marble version, just drop it in here using the same folder structure as in the ROM.

## If it bootloops

With `debug_adb` on, adb starts early in boot, so in most cases you can pull logs even while the phone is stuck on the boot animation:

```
adb wait-for-device logcat -b all > boot.log
adb shell dmesg > dmesg.log
```

Things worth searching for:

```
grep -iE "FATAL|vintf|avc: denied|init: .*failed|hidl|aidl" boot.log
```

If the phone keeps rebooting by itself, boot into OrangeFox and look in `/sys/fs/pstore/`. If the kernel has pstore enabled, the log from the previous boot ends up there.

## Repo layout

```
.github/workflows/port-hyperos.yml   the main workflow
scripts/port.sh                      the whole porting process lives here
scripts/lp_tool.py                   reads super & payload.bin metadata
scripts/fstab_patch.py               patches fstab
scripts/prop_merge.py                merges marble props into the port
scripts/prop_effective.py            shows which props actually apply at boot (init load order)
scripts/port_extras.sh               AOD overlay, Millet, device_features unlock, files from base
scripts/port_arch64.sh               64-bit-only donor fixes on top of the 64-32 marble vendor (ARCH64_FIX)
scripts/port_gms.sh                  copies Play Services / GSF / Play Store from the base when the donor has none
scripts/device_features_unlock.py    turns on features in device_features/*.xml
scripts/jar_smali_patch.py           patches SystemServerImpl in miui-services.jar (xiaomi.eu donors)
scripts/vintf_check.py               checks VINTF, vendor vs framework
scripts/linker_check.py              checks the libraries vendor needs
scripts/installer_sanitize.py        makes sure the installer never wipes data
scripts/sparse_split.py              splits super into super.img.0..8
scripts/apk_index.py                 reads package names from APKs
scripts/update-binary.in             fallback installer (when not using the base META-INF)
debloat_packages.txt                 the debloat list
devices/marble/                      marble-specific files
```

## Credits

- [toraidl/hyperos_port](https://github.com/toraidl/hyperos_port) and [toraidl/HyperOS-Port-Python](https://github.com/toraidl/HyperOS-Port-Python), the porting toolkit and references used here
- [sekaiacg/erofs-utils](https://github.com/sekaiacg/erofs-utils) for extract.erofs
- xiaomi.eu for the marble base ROM

---

Use at your own risk. If your phone bootloops, don't panic: you can always go back through OrangeFox or the official fastboot ROM.
