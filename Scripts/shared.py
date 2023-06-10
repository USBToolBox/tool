# pylint: disable=invalid-name
import enum
import sys
from time import time
from typing import Callable
from pathlib import Path

from Scripts._build import BUILD

VERSION = "0.2"

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    current_dir = Path(sys.executable).parent
    resource_dir = Path(sys._MEIPASS) / Path("resources")
else:
    current_dir = Path(__file__).parent.parent
    resource_dir = current_dir / Path("resources")


class USBDeviceSpeeds(enum.IntEnum):
    LowSpeed = 0
    FullSpeed = 1
    HighSpeed = 2
    SuperSpeed = 3
    # The integer value of this only applies for macOS
    SuperSpeedPlus = 4
    # This is not an actual value
    Unknown = 9999

    def __str__(self) -> str:
        return _usb_protocol_names[self]

    def __bool__(self) -> bool:
        return True


class USBPhysicalPortTypes(enum.IntEnum):
    USBTypeA = 0
    USBTypeMiniAB = 1
    ExpressCard = 2
    USB3TypeA = 3
    USB3TypeB = 4
    USB3TypeMicroB = 5
    USB3TypeMicroAB = 6
    USB3TypePowerB = 7
    USB3TypeC_USB2Only = 8
    USB3TypeC_WithSwitch = 9
    USB3TypeC_WithoutSwitch = 10
    Internal = 255

    def __str__(self) -> str:
        return _usb_physical_port_types[self]

    def __bool__(self) -> bool:
        return True


class USBControllerTypes(enum.IntEnum):
    UHCI = int("0x00", 16)
    OHCI = int("0x10", 16)
    EHCI = int("0x20", 16)
    XHCI = int("0x30", 16)
    Unknown = 9999

    def __str__(self) -> str:
        return _usb_controller_types[self]

    def __bool__(self) -> bool:
        return True


_usb_controller_types = {
    USBControllerTypes.UHCI: "USB 1.1 (UHCI)",
    USBControllerTypes.OHCI: "USB 1.1 (OHCI)",
    USBControllerTypes.EHCI: "USB 2.0 (EHCI)",
    USBControllerTypes.XHCI: "USB 3.0 (XHCI)",
    USBControllerTypes.Unknown: "Unknown",
}

_usb_physical_port_types = {
    USBPhysicalPortTypes.USBTypeA: "Type A",
    USBPhysicalPortTypes.USBTypeMiniAB: "Type Mini-AB",
    USBPhysicalPortTypes.ExpressCard: "ExpressCard",
    USBPhysicalPortTypes.USB3TypeA: "USB 3 Type A",
    USBPhysicalPortTypes.USB3TypeB: "USB 3 Type B",
    USBPhysicalPortTypes.USB3TypeMicroB: "USB 3 Type Micro-B",
    USBPhysicalPortTypes.USB3TypeMicroAB: "USB 3 Type Micro-AB",
    USBPhysicalPortTypes.USB3TypePowerB: "USB 3 Type Power-B",
    USBPhysicalPortTypes.USB3TypeC_USB2Only: "Type C - USB 2 only",
    USBPhysicalPortTypes.USB3TypeC_WithSwitch: "Type C - with switch",
    USBPhysicalPortTypes.USB3TypeC_WithoutSwitch: "Type C - without switch",
    USBPhysicalPortTypes.Internal: "Internal",
}

_short_names = True

_usb_protocol_names_full = {
    USBDeviceSpeeds.LowSpeed: "USB 1.1 (Low Speed)",
    USBDeviceSpeeds.FullSpeed: "USB 1.1 (Full Speed)",
    USBDeviceSpeeds.HighSpeed: "USB 2.0 (High Speed)",
    USBDeviceSpeeds.SuperSpeed: "USB 3.0/USB 3.1 Gen 1/USB 3.2 Gen 1x1 (SuperSpeed)",
    USBDeviceSpeeds.SuperSpeedPlus: "USB 3.1 Gen 2/USB 3.2 Gen 2×1 (SuperSpeed+)",
    USBDeviceSpeeds.Unknown: "Unknown",
}

_usb_protocol_names_short = {
    USBDeviceSpeeds.LowSpeed: "USB 1.1",
    USBDeviceSpeeds.FullSpeed: "USB 1.1",
    USBDeviceSpeeds.HighSpeed: "USB 2.0",
    USBDeviceSpeeds.SuperSpeed: "USB 3.0",
    USBDeviceSpeeds.SuperSpeedPlus: "USB 3.1 Gen 2",
    USBDeviceSpeeds.Unknown: "Unknown",
}

_usb_protocol_names = _usb_protocol_names_short if _short_names else _usb_protocol_names_full


def time_it(func: Callable, text: str, *args, **kwargs):
    start = time()
    result = func(*args, **kwargs)
    end = time()
    input(f"{text} took {end - start}, press enter to continue".strip())
    return result

debugging = False

def debug(str):
    if debugging:
        input(f"DEBUG: {str}\nPress enter to continue")

test_mode = False and debugging
if test_mode:
    debug_dump_path = Path(input("Debug dump path: ").strip().replace("'", "").replace('"', ""))
else:
    debug_dump_path = None

# def speed_to_name(speed: USBDeviceSpeeds):
#     return _usb_protocol_names[speed]
