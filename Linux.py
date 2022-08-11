from pathlib import Path
import subprocess
from Scripts import iokit, shared
from base import BaseUSBMap


def quick_read(path: Path):
    return path.read_text().strip()


def quick_read_2(path: Path, name: str):
    return quick_read(path / Path(name))


controller_paths: list[Path] = []


for bus_path in Path("/sys/bus/usb/devices").iterdir():
    # Only look at buses
    if not bus_path.stem.startswith("usb"):
        continue

    # The parent of the bus is the controller
    controller_paths.append(bus_path.resolve().parent)

for controller_path in controller_paths:
    print(f"Processing controller {controller_path}")

    lspci_output = subprocess.run(["lspci", "-vvvmm", "-s", controller_path.stem], stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()
    lspci_output = {i.partition(":\t")[0]: i.partition("\t")[2] for i in lspci_output.splitlines() if i}

    controller = {
        "name": lspci_output["Device"],
        "identifiers": {
            "bdf": [int(i, 16) for i in [controller_path.name[5:7], controller_path.name[8:10], controller_path.suffix[1]]],
            "pci_id": [quick_read_2(controller_path, "vendor")[2:], quick_read_2(controller_path, "device")[2:]],
        },
        "ports": []
    }

    if (controller_path / Path("revision")).exists():
        controller["identifiers"]["pci_revision"] = int(quick_read(controller_path / Path("revision")), 16)

    if (controller_path / Path("subsystem_vendor")).exists() and (controller_path / Path("subsystem_device")).exists():
        controller["identifiers"]["pci_id"] += [quick_read_2(controller_path, "subsystem_vendor")[2:], quick_read_2(controller_path, "subsystem_device")[2:]]

    if (controller_path / Path("firmware_node/path")).exists():
        controller["identifiers"]["acpi_path"] = quick_read_2(controller_path, "firmware_node/path")

    controller["class"] = shared.USBControllerTypes(int(quick_read(controller_path / Path("class")), 16) & 0xff)

    # Enumerate the buses
    for hub in controller_path.glob("usb*"):
        
