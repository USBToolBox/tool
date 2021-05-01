import binascii
import copy
from enum import Enum
from operator import itemgetter

from Scripts import iokit, shared
from base import BaseUSBMap

# from gui import *


class IOEntryProperties(Enum):
    NAME = "IORegistryEntryName"
    CHILDREN = "IORegistryEntryChildren"
    CLASS = "IOClass"
    OBJECT_CLASS = "IOObjectClass"
    ADDRESS = "IOChildIndex"


def hexswap(input_hex: str) -> str:
    hex_pairs = [input_hex[i : i + 2] for i in range(0, len(input_hex), 2)]
    hex_rev = hex_pairs[::-1]
    hex_str = "".join(["".join(x) for x in hex_rev])
    return hex_str.upper()


def read_property(input_value: bytes, places: int) -> str:
    return binascii.hexlify(input_value).decode()[:-places]


class macOSUSBMap(BaseUSBMap):
    @staticmethod
    def port_class_to_type(speed):
        if "AppleUSB30XHCIPort" in speed:
            return shared.USBDeviceSpeeds.SuperSpeed
        elif set(["AppleUSB20XHCIPort", "AppleUSBEHCIPort"]) & set(speed):
            return shared.USBDeviceSpeeds.HighSpeed
        elif set(["AppleUSBOHCIPort", "AppleUSBUHCIPort"]) & set(speed):
            return shared.USBDeviceSpeeds.FullSpeed
        else:
            shared.debug(f"Unknown port type for {speed}!")
            return shared.USBDeviceSpeeds.Unknown

    @staticmethod
    def controller_class_to_type(parent_props, controller_props, inheritance):
        # Check class code
        if "class-code" in parent_props:
            return shared.USBControllerTypes(parent_props["class-code"][0])
        # Check class type
        elif "AppleUSBXHCI" in inheritance:
            return shared.USBControllerTypes.XHCI
        elif "AppleUSBEHCI" in inheritance:
            return shared.USBControllerTypes.EHCI
        elif "AppleUSBOHCI" in inheritance:
            return shared.USBControllerTypes.OHCI
        elif "AppleUSBUHCI" in inheritance:
            return shared.USBControllerTypes.UHCI
        else:
            shared.debug(f"Unknown controller type for class code {read_property(parent_props['class-code'], 2) if 'class-code' in parent_props else 'none'}, inheritance {inheritance}!")
            return shared.USBControllerTypes.Unknown

    def get_controllers(self):
        controllers = []

        err, controller_iterator = iokit.IOServiceGetMatchingServices(iokit.kIOMasterPortDefault, iokit.IOServiceMatching("AppleUSBHostController".encode()), None)
        for controller_instance in iokit.ioiterator_to_list(controller_iterator):
            controller_properties: dict = iokit.corefoundation_to_native(iokit.IORegistryEntryCreateCFProperties(controller_instance, None, iokit.kCFAllocatorDefault, iokit.kNilOptions)[1])  # type: ignore

            err, parent_device = iokit.IORegistryEntryGetParentEntry(controller_instance, "IOService".encode(), None)
            parent_properties: dict = iokit.corefoundation_to_native(iokit.IORegistryEntryCreateCFProperties(parent_device, None, iokit.kCFAllocatorDefault, iokit.kNilOptions)[1])  # type: ignore

            controller = {
                "name": iokit.io_name_t_to_str(iokit.IORegistryEntryGetName(parent_device, None)[1]),
                # "class": macOSUSBMap.port_class_to_type(iokit.get_class_inheritance(controller_instance)),
                "identifiers": {"location_id": controller_properties["locationID"], "path": iokit.IORegistryEntryCopyPath(controller_instance, "IOService".encode())},
                "ports": [],
            }
            if set(["vendor-id", "device-id"]) & set(parent_properties.keys()):
                controller["identifiers"]["pci_id"] = [hexswap(read_property(parent_properties[i], 4)).lower() for i in ["vendor-id", "device-id"]]

            if set(["subsystem-vendor-id", "subsystem-id"]) & set(parent_properties.keys()):
                controller["identifiers"]["pci_id"] += [hexswap(read_property(parent_properties[i], 4)).lower() for i in ["subsystem-vendor-id", "subsystem-id"]]

            if "revision-id" in parent_properties:
                controller["identifiers"]["pci_revision"] = int(hexswap(read_property(parent_properties.get("revision-id", b""), 6)), 16)

            if "acpi-path" in parent_properties:
                controller["identifiers"]["acpi_path"] = "\\" + ".".join([i.split("@")[0] for i in parent_properties["acpi-path"].split("/")[1:]])

            if "pcidebug" in parent_properties:
                controller["identifiers"]["bdf"] = [int(i) for i in parent_properties["pcidebug"].split(":", 3)[:3]]

            if "bus-number" in parent_properties:
                # TODO: Properly figure out max value
                controller["identifiers"]["bus_number"] = int(hexswap(read_property(parent_properties["bus-number"], 6)), 16)

            controller["class"] = self.controller_class_to_type(parent_properties, controller_properties, iokit.get_class_inheritance(controller_instance))

            err, port_iterator = iokit.IORegistryEntryGetChildIterator(controller_instance, "IOService".encode(), None)
            for port in iokit.ioiterator_to_list(port_iterator):
                port_properties: dict = iokit.corefoundation_to_native(iokit.IORegistryEntryCreateCFProperties(port, None, iokit.kCFAllocatorDefault, iokit.kNilOptions)[1])  # type: ignore
                controller["ports"].append(
                    {
                        "name": iokit.io_name_t_to_str(iokit.IORegistryEntryGetName(port, None)[1]),
                        "comment": None,
                        "index": int(read_property(port_properties["port"], 6), 16),
                        "class": macOSUSBMap.port_class_to_type(iokit.get_class_inheritance(port)),
                        "type": None,
                        "guessed": shared.USBPhysicalPortTypes.USB3TypeC_WithSwitch
                        if set(iokit.get_class_inheritance(port)) & set(["AppleUSB20XHCITypeCPort", "AppleUSB30XHCITypeCPort"])
                        else port_properties.get("UsbConnector"),
                        "location_id": port_properties["locationID"],
                        "devices": [],
                    }
                )
                iokit.IOObjectRelease(port)
            controllers.append(controller)

            iokit.IOObjectRelease(controller_instance)
            iokit.IOObjectRelease(parent_device)
        self.controllers = controllers
        if not self.controllers_historical:
            self.controllers_historical = copy.deepcopy(self.controllers)
        else:
            self.merge_controllers(self.controllers_historical, self.controllers)
        self.update_devices()

    def recurse_devices(self, iterator):
        props = []
        iokit.IORegistryIteratorEnterEntry(iterator)
        device = iokit.IOIteratorNext(iterator)
        while device:
            props.append(
                {
                    "name": iokit.io_name_t_to_str(iokit.IORegistryEntryGetName(device, None)[1]),
                    "port": iokit.IORegistryEntryCreateCFProperty(device, "PortNum", iokit.kCFAllocatorDefault, iokit.kNilOptions),
                    "location_id": iokit.IORegistryEntryCreateCFProperty(device, "locationID", iokit.kCFAllocatorDefault, iokit.kNilOptions),
                    "speed": shared.USBDeviceSpeeds(iokit.IORegistryEntryCreateCFProperty(device, "Device Speed", iokit.kCFAllocatorDefault, iokit.kNilOptions)),  # type: ignore
                    "devices": self.recurse_devices(iterator),
                }
            )
            iokit.IOObjectRelease(device)
            device = iokit.IOIteratorNext(iterator)
        iokit.IORegistryIteratorExitEntry(iterator)
        props.sort(key=itemgetter("name"))
        return props

    def update_devices(self):
        # Reset devices
        for controller in self.controllers:
            for port in controller["ports"]:
                port["devices"] = []

        err, usb_plane_iterator = iokit.IORegistryCreateIterator(iokit.kIOMasterPortDefault, "IOUSB".encode(), 0, None)
        controller_instance = iokit.IOIteratorNext(usb_plane_iterator)
        while controller_instance:
            location_id = iokit.corefoundation_to_native(iokit.IORegistryEntryCreateCFProperty(controller_instance, "locationID", iokit.kCFAllocatorDefault, iokit.kNilOptions))

            controller = [i for i in self.controllers if i["identifiers"]["location_id"] == location_id][0]
            # This is gonna be a controller

            devices = self.recurse_devices(usb_plane_iterator)

            for port in controller["ports"]:
                port["devices"] = [i for i in devices if i["port"] == port["index"] or i["location_id"] == port["location_id"]]

            iokit.IOObjectRelease(controller_instance)
            controller_instance = iokit.IOIteratorNext(usb_plane_iterator)
        iokit.IOObjectRelease(usb_plane_iterator)

        self.merge_devices(self.controllers_historical, self.controllers)


e = macOSUSBMap()
