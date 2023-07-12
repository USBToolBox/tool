import copy
import re
import subprocess
from operator import itemgetter
from pathlib import Path

from base import BaseUSBMap
from Scripts import shared


def quick_read(path: Path):
    return path.read_text().strip("\x00").strip()


def quick_read_2(path: Path, name: str):
    return quick_read(path / name)


class LinuxUSBMap(BaseUSBMap):
    def enumerate_hub(self, hub: Path):
        bus_number = quick_read_2(hub, "busnum")
        hub_info = {
            "hub_name": hub.name,
            "port_count": int(quick_read_2(hub, "maxchild")),
            "speed": shared.USBDeviceSpeeds.from_speed(int(quick_read_2(hub, "speed"))),
            "version": quick_read_2(hub, "version"),
            "ports": [],
        }

        # Get the ports
        ports = hub.glob(f"{bus_number}-0:1.0/usb{bus_number}-port*")
        for i, port in enumerate(sorted(ports, key=lambda x: int(x.name.replace(f"usb{bus_number}-port", "")))):
            port_info = {
                "name": quick_read_2(port, "firmware_node/path").split(".")[-1] if (port / "firmware_node/path").exists() else f"Port {i}",
                "comment": None,
                "index": int(port.name.replace(f"usb{bus_number}-port", "")),  # Need to parse it from the name. I hate linux
                "class": hub_info["speed"],  # tbd
                "type": None,
                "guessed": None,  # tbd
                "connect_type": quick_read_2(port, "connect_type"),
                "devices": [],
                "type_c": False,
                "path": str(port),
            }

            if (port / "peer").exists():
                port_info["companion_info"] = re.match(r"(?P<hub>usb\d+)-port(?P<port>\d+)", (port / "peer").resolve().name).groupdict()
            else:
                port_info["companion_info"] = {"hub": "", "port": ""}

            if (port / "connector").exists():
                # I think this is only USB-C
                port_info["type_c"] = True
                other_ports = [i for i in (port / "connector").glob("usb*-port*") if i.resolve() != port.resolve()]
                assert len(other_ports) == 1
                if (port / "peer").exists():
                    assert port_info["companion_info"] == re.match(r"(?P<hub>usb\d+)-port(?P<port>\d+)", other_ports[0].resolve().name).groupdict()
                port_info["companion_info"] = re.match(r"(?P<hub>usb\d+)-port(?P<port>\d+)", other_ports[0].resolve().name).groupdict()

            if (port / "device").exists():
                device = port / "device"
                device_info = {
                    # TODO: Use lsusb?
                    "name": f"{quick_read_2(device, 'manufacturer')} {quick_read_2(device, 'product')}" if (device / "manufacturer").exists() else "Unknown Device",
                    "speed": shared.USBDeviceSpeeds.from_speed(int(quick_read_2(device, "speed"))),
                    "devices": [],  # I'm not dealing with this rn
                }

                if int(quick_read_2(device, "bDeviceClass"), 16) == 9 or (device / "maxchild").exists():
                    # This is a hub. Enumerate.
                    device_info["devices"] = self.enumerate_hub(device)

                port_info["devices"].append(device_info)

            hub_info["ports"].append(port_info)
        hub_info["ports"].sort(key=itemgetter("index"))
        return hub_info

    def get_controllers(self):
        controller_paths: set[Path] = set()

        for bus_path in Path("/sys/bus/usb/devices").iterdir():
            # Only look at buses
            if not bus_path.stem.startswith("usb"):
                continue

            # The parent of the bus is the controller
            controller_paths.add(bus_path.resolve().parent)

        controllers = []

        for controller_path in sorted(controller_paths):
            print(f"Processing controller {controller_path}")

            lspci_output = subprocess.run(["lspci", "-vvvmm", "-s", controller_path.stem], stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()
            lspci_output = {i.partition(":\t")[0]: i.partition("\t")[2] for i in lspci_output.splitlines() if i}

            controller = {
                "name": lspci_output["Device"],
                "identifiers": {
                    "bdf": [int(i, 16) for i in [controller_path.name[5:7], controller_path.name[8:10], controller_path.suffix[1]]],
                    "pci_id": [quick_read_2(controller_path, "vendor")[2:], quick_read_2(controller_path, "device")[2:]],
                },
                "ports": [],
            }

            if (controller_path / "revision").exists():
                controller["identifiers"]["pci_revision"] = int(quick_read(controller_path / "revision"), 16)

            if (controller_path / "subsystem_vendor").exists() and (controller_path / "subsystem_device").exists():
                controller["identifiers"]["pci_id"] += [quick_read_2(controller_path, "subsystem_vendor")[2:], quick_read_2(controller_path, "subsystem_device")[2:]]

            if (controller_path / "firmware_node/path").exists():
                controller["identifiers"]["acpi_path"] = quick_read_2(controller_path, "firmware_node/path")

            controller["class"] = shared.USBControllerTypes(int(quick_read_2(controller_path, "class"), 16) & 0xFF)

            # Enumerate the buses
            for hub in sorted(controller_path.glob("usb*")):
                # maxchild, speed, version
                controller |= self.enumerate_hub(hub)

            controllers.append(controller)

        self.controllers = controllers
        if not self.controllers_historical:
            self.controllers_historical = copy.deepcopy(self.controllers)
        else:
            self.merge_controllers(self.controllers_historical, self.controllers)

    def update_devices(self):
        self.get_controllers()


e = LinuxUSBMap()
