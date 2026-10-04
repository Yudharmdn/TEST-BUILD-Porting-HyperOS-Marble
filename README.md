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
- **fstab and vbmeta:** `/data` encryption is removed, vendor/odm can be mounted rw, and verity is disabled.
- **Keyboard:** Gboard is added as a system app, and the Chinese keyboards (Sogou, Baidu, iFlytek) are removed. With no other keyboard left, Gboard becomes the default on its own.
- **Debloat:** unneeded apps are removed based on `debloat_packages.txt`.
- **boot.img:** the stock marble kernel from the base ROM is used by default (`BOOT_IMG: ""` in the workflow), which is the safest choice for a first flash. Put a URL in `BOOT_IMG` to use a custom kernel instead. The build then checks that it still has a ramdisk (marble has no init_boot, so first-stage init lives there) and that the kernel is the same 5.10 series as the base, since the modules in vendor_boot and vendor_dlkm are built for it.

## What's inside the zip

```
META-INF/                 installer from xiaomi.eu
images/abl.img ... xbl_ramdump.img   marble firmware
images/boot.img           kernel (stock by default)
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
| `ext4_partitions` | `vendor odm`, so they can be edited directly on the phone |
| `debloat` | extra paths to remove, space separated. Can be left empty |
| `disable_encryption` | leave it `true` |
| `rw_mount` | leave it `true` |
| `debug_adb` | `true` while testing (adb is on from boot, handy for logcat). Turn it off once things are stable |
| `recovery_img_url` | leave it empty |
| `release_repo` | empty = output goes to Artifacts. Set it to `owner/repo` to upload to a Release instead (needs the `RELEASE_TOKEN` secret) |

4. Wait for it to finish, then grab the zip from the **Artifacts** section of the run page. Artifacts are kept for 7 days.

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
- **NFC:** disabled (`NQNfcNci` is removed). If you need NFC, delete that line from `debloat_packages.txt` and rebuild.
- **Other things that are gone:** Print, SIM Toolkit, the QR Scanner, Find Device, and Joyose (game profiles).

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
devices/marble/product/overlay/               DevicesOverlay.apk, DevicesAndroidOverlay.apk
```

If there's anything else you want forced to the marble version, just drop it in here using the same folder structure as in the ROM.

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
