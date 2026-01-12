# USBToolBoxᵇᵉᵗᵃ

*Making USB mapping simple(r)*

The USBToolBox tool is a USB mapping tool supporting Windows, macOS, and Linux. It allows for building a custom injector kext from Windows and macOS, with Linux support for USB topology preparation.

## Features

* Supports mapping from Windows, macOS, and Linux (preparation mode)
* Can build a map using either the USBToolBox kext or native Apple kexts (AppleUSBHostMergeProperties)
* Supports multiple ways of matching
* Supports companion ports (on Windows)
* Make educated guesses for port types (on Windows)
* Generate USB blueprints for macOS import (on Linux)

## Supported Methods

### From Windows

Windows 10 or 11 64-bit are recommended for the full feature set (companion port binding, port type guessing.). Windows 8 may work, Windows 7 and below will very likely crash. 32-bit is not supported, macOS needs 64-bit anyway.

Simply download the latest `Windows.exe` from releases. If Windows Defender/other antivirus complains, you can either whitelist the download or use `Windows.zip`, which doesn't have a self extractor (which is what most antiviruses seem to complain about).

### From Windows PE

Yes this works lol. Some device names may not be as descriptive but if you really don't want to install Windows, you can create a Windows PE USB and hit Shift + F10 to open `cmd`, then run the program.

### From macOS

macOS is *not* recommended for several reasons. You won't have features like guessing port types (as there simply isn't enough info for this) as well as binding companion ports (again, no info). However, there's also port limits to deal with, and in macOS 11.3, `XhciPortLimit` is broken, resulting in a lot more hoops to go through. If you are forced to use macOS, you should probably use [USBMap](https://github.com/CorpNewt/USBMap) instead, as it has code to handle the port limit.

If you still want to use USBToolBox on macOS, download `macOS.zip` from releases.

### From Linux (Preparation Mode)

Linux support allows you to **prepare** your USB mapping before installing macOS. This is useful for:

* Documenting your USB topology before macOS installation
* Identifying internal devices (Bluetooth, webcam, fingerprint readers)
* Generating a blueprint to import into macOS later

**Requirements:** Python 3.6+, `lspci` (pciutils), `lsusb` (usbutils)

**Usage:**

```bash
python3 Linux.py
```

**Features:**

* Detects XHCI/EHCI controllers via lspci
* Enumerates USB devices and port topology
* Generates JSON blueprint for macOS import
* Provides OpenCore configuration guidance

**Limitations:**

* ⚠️ **Preparation only** - Cannot build final kext (must be done in macOS)
* Cannot detect physical connector types (Type-A vs Type-C)
* No live plug/unplug detection (snapshot-based)
* Devices through hubs shown separately

After generating your blueprint, see `docs/linux_to_macos_handoff.md` for instructions on finalizing your USB map in macOS using Hackintool.

## Usage

This is gonna be a very basic guide for now. A fully-fleshed guide will be released in the future.

1. Download the appropriate download for your OS.
2. Open and adjust settings if necessary.
3. Select Discover Ports and wait for the listing to populate.
4. Plug in a USB device into each port. Wait for the listing to show your USB device before unplugging it and plugging it into another port.
    * If on Windows, you only need to plug in 1 device to USB 3 ports (as companion detection should be working). If on macOS, you will have to plug in a USB 2 device and a USB 3 device into each USB 3 port.
    * For old computers with OHCI/UHCI and EHCI controllers, you will need to plug in a mouse/keyboard to map the USB 1.1 personalities, as most USB 2 devices will end on the USB 2 personality.
5. Once mapping is done, go to the Select Ports screen.
6. Select your ports and adjust port types as neccesary.
7. Press K to build the kext!
8. Add the resulting USB map to your `EFI/OC/Kexts` folder, and make sure to update your `config.plist`.
    * If building a map that uses the USBToolBox kext, make sure to grab the [latest release](https://github.com/USBToolBox/kext/releases) of the kext too.
    * Make sure to remove `UTBDefault.kext` <!-- i need a better name for this lol -->, if you have it.
9. Reboot and you should have your USB map working!

## Known Issues/FAQ

See the [issues tab](https://github.com/USBToolBox/tool/issues) for known issues.

### FAQ

* Q: Why is some information missing?

  A: Make sure you have drivers installed for all your devices. On Windows, some information is missing if you don't have drivers installed, leading USBToolBox to report them as unknown.

* Q: How do I report a bug?

  A: Please go to the [new issue](https://github.com/USBToolBox/tool/issues/new/choose) page, click on "Bug report", and read through the steps before filling them out. Please ensure that you respond to my inquiries as there's no other way I can fix bugs.

## Credits

@CorpNewt for [USBMap](https://github.com/corpnewt/USBMap). This project was heavily inspired by USBMap (and some functions are from USBMap).

My testing team (you know who you are) for testing
