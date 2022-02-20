# USBDump Conversion Interface
import itertools
import json
import subprocess
import sys
from operator import itemgetter
from pathlib import Path

from Scripts import shared

# input_path = input("File path: ")
# if input_path:
#     file_path = Path("samples/" + input_path)
# else:
#     file_path = Path("samples/tablet.json")
# info = json.load(file_path.open())


hub_map = {}


def get_port_type(port):
    if not port["ConnectionInfoV2"]:
        return shared.USBDeviceSpeeds.Unknown
    supported_usb_protocols = port["ConnectionInfoV2"]["SupportedUsbProtocols"]
    if supported_usb_protocols["Usb300"]:
        return shared.USBDeviceSpeeds.SuperSpeed
    elif supported_usb_protocols["Usb200"] and supported_usb_protocols["Usb110"]:
        return shared.USBDeviceSpeeds.HighSpeed
    elif supported_usb_protocols["Usb110"]:
        return shared.USBDeviceSpeeds.FullSpeed
    else:
        return shared.USBDeviceSpeeds.Unknown


def get_device_speed(port):
    speed = port["ConnectionInfo"]["Speed"]
    if speed == shared.USBDeviceSpeeds.LowSpeed:
        return (shared.USBDeviceSpeeds.LowSpeed, None)
    elif speed == shared.USBDeviceSpeeds.FullSpeed:
        speed = shared.USBDeviceSpeeds.FullSpeed
    elif speed == shared.USBDeviceSpeeds.HighSpeed:
        speed = shared.USBDeviceSpeeds.HighSpeed
    elif speed == shared.USBDeviceSpeeds.SuperSpeed and port["ConnectionInfoV2"] and port["ConnectionInfoV2"]["Flags"]["DeviceIsOperatingAtSuperSpeedPlusOrHigher"]:
        return (shared.USBDeviceSpeeds.SuperSpeedPlus, None)
    elif speed == shared.USBDeviceSpeeds.SuperSpeed:
        speed = shared.USBDeviceSpeeds.SuperSpeed
    else:
        return (shared.USBDeviceSpeeds.Unknown, speed)

    if port["ConnectionInfoV2"] and port["ConnectionInfoV2"]["Flags"]["DeviceIsSuperSpeedPlusCapableOrHigher"]:
        return (speed, shared.USBDeviceSpeeds.SuperSpeedPlus)
    elif speed < shared.USBDeviceSpeeds.SuperSpeed and port["ConnectionInfoV2"] and port["ConnectionInfoV2"]["Flags"]["DeviceIsSuperSpeedCapableOrHigher"]:
        return (speed, shared.USBDeviceSpeeds.SuperSpeed)
    else:
        return (speed, None)


def get_device_speed_string(port, hub_port_count=None):
    speed = get_device_speed(port)
    # return f"{speed[0]}{(', ' + speed[1] + ' capable') if speed[1] else ''}{(', ' + str(hub_port_count) + ' ports') if hub_port_count else ''}"
    return speed[0]


def get_device_name(port):
    if not port["UsbDeviceProperties"]:
        port["UsbDeviceProperties"] = {}
    if not port["DeviceInfoNode"]:
        port["DeviceInfoNode"] = {}

    if not port["ConnectionInfo"]["DeviceDescriptor"]["iProduct"]:
        return port["UsbDeviceProperties"].get("DeviceDesc") or port["DeviceInfoNode"].get("DeviceDescName", "Unknown Device")
    for string_desc in port["StringDescs"] or []:
        if string_desc["DescriptorIndex"] == port["ConnectionInfo"]["DeviceDescriptor"]["iProduct"]:
            return string_desc["StringDescriptor"][0]["bString"]
    return port["UsbDeviceProperties"].get("DeviceDesc") or port["DeviceInfoNode"].get("DeviceDescName", "Unknown Device")


def get_hub_type(port):
    return shared.USBDeviceSpeeds(port["HubInfoEx"]["HubType"])


# def merge_companions(controllers):
#     controllers = copy.deepcopy(controllers)
#     for controller in controllers:
#         for port in controller["ports"]:
#             if port["companion_info"]["port"]:
#                 companion_hub = [i for i in controllers if i["hub_name"] == port["companion_info"]["hub"]][0]
#                 companion_port = [i for i in companion_hub["ports"] if i["index"] == port["companion_info"]["port"]][0]
#                 companion_port["companion_info"]["port"] = 0
#                 port["companion_info"]["port"] = companion_port
#     for controller in controllers:
#         for port in list(controller["ports"]):
#             if port["companion_info"]["port"]:
#                 companion_hub = [i for i in controllers if i["hub_name"] == port["companion_info"]["hub"]][0]
#                 companion_port = [i for i in companion_hub["ports"] if i["index"] == port["companion_info"]["port"]["index"]][0]
#                 companion_hub["ports"].remove(companion_port)
#     return controllers


def get_hub_by_name(name):
    return hub_map.get(name)

# TODO: Figure out how to deal with the hub name not matching
def get_companion_port(port):
    return ([i for i in hub_map.get(port["companion_info"]["hub"], {"ports": []})["ports"] if i["index"] == port["companion_info"]["port"]] or [None])[0]


def guess_ports():
    for hub in hub_map:
        for port in hub_map[hub]["ports"]:
            if not port["status"].endswith("DeviceConnected"):
                # we don't have info. anything else is going to error
                port["guessed"] = None
            elif port["type_c"] or port["companion_info"]["port"] and get_companion_port(port) and get_companion_port(port).get("type_c", None):
                port["guessed"] = shared.USBPhysicalPortTypes.USB3TypeC_WithSwitch
            elif not port["user_connectable"]:
                port["guessed"] = shared.USBPhysicalPortTypes.Internal
            elif (
                port["class"] == shared.USBDeviceSpeeds.SuperSpeed
                and port["companion_info"]["port"]
                and get_companion_port(port)
                and get_companion_port(port)["class"] == shared.USBDeviceSpeeds.HighSpeed
                or port["class"] == shared.USBDeviceSpeeds.HighSpeed
                and port["companion_info"]["port"]
                and get_companion_port(port)
                and get_companion_port(port)["class"] == shared.USBDeviceSpeeds.SuperSpeed
            ):
                port["guessed"] = shared.USBPhysicalPortTypes.USB3TypeA
            elif port["class"] == shared.USBDeviceSpeeds.SuperSpeed and not port["companion_info"]["port"]:
                port["guessed"] = shared.USBPhysicalPortTypes.Internal
            else:
                port["guessed"] = shared.USBPhysicalPortTypes.USBTypeA


def serialize_hub(hub):
    hub_info = {
        "hub_name": hub["HubName"],
        # "class": get_hub_type(hub),
        "port_count": hub["HubInfo"]["HubInformation"]["HubDescriptor"]["bNumberOfPorts"],
        # "highest_port_number": hub["HubInfoEx"]["HighestPortNumber"],
        "ports": [],
    }

    # HubPorts
    hub_ports = hub["HubPorts"]
    if hub_ports:  # For some reason, this is sometimes null? Botched driver?
        for i, port in enumerate(hub_ports):
            if not port:
                continue
            port_info = {
                "index": (port.get("PortConnectorProps") or {}).get("ConnectionIndex")
                or (port.get("ConnectionInfo") or {}).get("ConnectionIndex")
                or (port.get("ConnectionInfoV2") or {}).get("ConnectionIndex")
                or i + 1,
                "comment": None,
                "class": shared.USBDeviceSpeeds.Unknown,
                "status": port["ConnectionInfo"]["ConnectionStatus"],
                "type": None,
                "guessed": None,
                "devices": [],
            }
            port_info["name"] = f"Port {port_info['index']}"

            friendly_error = {"DeviceCausedOvercurrent": "Device connected to port pulled too much current."}

            if not port_info["status"].endswith("DeviceConnected"):
                # shared.debug(f"Device connected to port {port_info['index']} errored. Please unplug or connect a different device.")
                port_info["devices"] = [{"error": friendly_error.get(port_info["status"], True)}]
                hub_info["ports"].append(port_info)
                continue

            port_info["class"] = get_port_type(port)
            if not port["PortConnectorProps"]:
                port["PortConnectorProps"] = {}

            port_info["companion_info"] = {
                "port": port["PortConnectorProps"].get("CompanionPortNumber", ""),
                "hub": port["PortConnectorProps"].get("CompanionHubSymbolicLinkName", ""),
                "multiple_companions": bool(port["PortConnectorProps"].get("UsbPortProperties", {}).get("PortHasMultipleCompanions", False)),
            }
            port_info["type_c"] = bool(port["PortConnectorProps"].get("UsbPortProperties", {}).get("PortConnectorIsTypeC", False))
            port_info["user_connectable"] = bool(port["PortConnectorProps"].get("UsbPortProperties", {}).get("PortIsUserConnectable", True))

            # Guess port type

            if port["ConnectionInfo"]["ConnectionStatus"] == "DeviceConnected":
                device_info = {"name": get_device_name(port), "instance_id": port["UsbDeviceProperties"].get("DeviceId"), "devices": []}

                if port["DeviceInfoType"] == "ExternalHubInfo":
                    external_hub = serialize_hub(port)
                    device_info["speed"] = get_device_speed_string(port, external_hub["port_count"])
                    device_info["devices"] = [i for i in itertools.chain.from_iterable([hub_port["devices"] for hub_port in external_hub["ports"]]) if i]
                    # device_info["hub_type"] = get_hub_type(port)
                    # device_info["hub"] = serialize_hub(port)
                else:
                    device_info["speed"] = get_device_speed_string(port)

                port_info["devices"].append(device_info)

            hub_info["ports"].append(port_info)
    hub_info["ports"].sort(key=itemgetter("index"))
    hub_map[hub_info["hub_name"]] = hub_info
    return hub_info


def get_controllers():
    new_info = []

    usbdump_path = Path("resources/usbdump.exe")

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        usbdump_path = Path(sys._MEIPASS) / usbdump_path

    info = json.load(shared.debug_dump_path.open())["usbdump"] if shared.test_mode else json.loads(subprocess.run(usbdump_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode())
    for controller in info:
        if not controller["RootHub"]:
            # This is useless
            continue

        # root
        controller_info = {
            "name": controller["UsbDeviceProperties"]["DeviceDesc"],
            "identifiers": {
                "instance_id": controller["UsbDeviceProperties"]["DeviceId"],
                # "revision": controller["Revision"],
            },
            # "port_count_no3": controller["ControllerInfo"]["NumberOfRootPorts"],
            "class": "",
        } | serialize_hub(controller["RootHub"])

        if all(controller[i] not in [0, int("0xFFFF", 16)] for i in ["VendorID", "DeviceID"]):
            controller_info["identifiers"]["pci_id"] = [hex(controller[i])[2:] for i in ["VendorID", "DeviceID"]]

        if controller["SubSysID"] not in [0, int("0xFFFFFFFF", 16)]:
            controller_info["identifiers"]["pci_id"] += [hex(controller["SubSysID"])[2:6], hex(controller["SubSysID"])[6:]]

        if (controller.get("ControllerInfo") or {}).get("PciRevision", 0) not in [0, int("0xFF", 16)]:
            controller_info["identifiers"]["pci_revision"] = int(controller["ControllerInfo"]["PciRevision"])

        if controller["BusDeviceFunctionValid"]:
            controller_info["identifiers"]["bdf"] = [controller["BusNumber"], controller["BusDevice"], controller["BusFunction"]]

        new_info.append(controller_info)
    guess_ports()
    if False:
        for hub in hub_map:
            for port in hub_map[hub]["ports"]:
                if port["companion_info"]["hub"]:
                    port["companion_info"]["hub"] = hub_map[port["companion_info"]["hub"]]
    return new_info
