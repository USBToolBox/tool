#!/usr/bin/env python3
"""
Linux USB Port Mapping Tool for Hackintosh
Part of USBToolBox - Linux Implementation

This module provides USB controller and device detection on Linux systems
for preparing USB port mappings for macOS Hackintosh installations.

IMPORTANT LIMITATIONS:
- This is a PREPARATION tool, not a final kext generator
- Port connector types (Type-A vs Type-C) cannot be determined from Linux
- Final USB mapping must be completed in macOS using Hackintool or similar

Supported macOS versions: Sonoma, Sequoia, Tahoe 26

STANDALONE VERSION: Does not require termcolor2 or base.py
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Optional, List, Dict, Any


# Color Output (ANSI codes - no external dependency)

class Colors:
    """ANSI color codes for terminal output."""
    BLUE = "\033[36;1m"
    GREEN = "\033[32;1m"
    YELLOW = "\033[33;1m"
    RED = "\033[31;1m"
    RESET = "\033[0m"
    
    @classmethod
    def disable(cls):
        """Disable colors for non-TTY output."""
        cls.BLUE = cls.GREEN = cls.YELLOW = cls.RED = cls.RESET = ""


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# Enums (Self-contained, matching shared.py)

class USBDeviceSpeeds(IntEnum):
    """USB device speed classifications."""
    LowSpeed = 0
    FullSpeed = 1
    HighSpeed = 2
    SuperSpeed = 3
    SuperSpeedPlus = 4
    Unknown = 9999
    
    def __str__(self) -> str:
        speed_names = {
            USBDeviceSpeeds.LowSpeed: "USB 1.1 (Low)",
            USBDeviceSpeeds.FullSpeed: "USB 1.1 (Full)",
            USBDeviceSpeeds.HighSpeed: "USB 2.0",
            USBDeviceSpeeds.SuperSpeed: "USB 3.0",
            USBDeviceSpeeds.SuperSpeedPlus: "USB 3.1+",
            USBDeviceSpeeds.Unknown: "Unknown",
        }
        return speed_names.get(self, "Unknown")


class USBPhysicalPortTypes(IntEnum):
    """USB physical port/connector types (per ACPI spec)."""
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
        type_names = {
            USBPhysicalPortTypes.USBTypeA: "Type A (USB 2)",
            USBPhysicalPortTypes.USB3TypeA: "USB 3 Type A",
            USBPhysicalPortTypes.USB3TypeC_WithSwitch: "Type C (with switch)",
            USBPhysicalPortTypes.USB3TypeC_WithoutSwitch: "Type C (no switch)",
            USBPhysicalPortTypes.Internal: "Internal",
        }
        return type_names.get(self, f"Type {int(self)}")


class USBControllerTypes(IntEnum):
    """USB host controller types."""
    UHCI = 0x00
    OHCI = 0x10
    EHCI = 0x20
    XHCI = 0x30
    Unknown = 9999
    
    def __str__(self) -> str:
        ctrl_names = {
            USBControllerTypes.UHCI: "USB 1.1 (UHCI)",
            USBControllerTypes.OHCI: "USB 1.1 (OHCI)",
            USBControllerTypes.EHCI: "USB 2.0 (EHCI)",
            USBControllerTypes.XHCI: "USB 3.0 (XHCI)",
            USBControllerTypes.Unknown: "Unknown",
        }
        return ctrl_names.get(self, "Unknown")


# Data Classes for USB Topology

@dataclass
class USBDevice:
    """Represents a connected USB device."""
    name: str
    vendor_id: str = ""
    product_id: str = ""
    bus: int = 0
    device: int = 0
    port: int = 0
    speed: str = ""
    speed_class: Optional[USBDeviceSpeeds] = None
    instance_id: str = ""
    is_hub: bool = False
    children: List['USBDevice'] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "speed": self.speed,
            "instance_id": self.instance_id,
        }
        if self.children:
            result["devices"] = [c.to_dict() for c in self.children]
        return result


@dataclass
class USBPort:
    """Represents a USB port on a controller."""
    index: int
    name: str = ""
    port_class: Optional[USBDeviceSpeeds] = None
    devices: List[USBDevice] = field(default_factory=list)
    comment: Optional[str] = None
    guessed_type: Optional[USBPhysicalPortTypes] = None
    companion_port: Optional[int] = None
    is_internal: bool = False
    type_c: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "class": str(self.port_class) if self.port_class else "Unknown",
            "comment": self.comment,
            "guessed": str(self.guessed_type) if self.guessed_type else None,
            "devices": [d.to_dict() for d in self.devices],
        }


@dataclass 
class USBController:
    """Represents a USB host controller."""
    name: str
    pci_id: List[str] = field(default_factory=list)
    acpi_path: str = ""
    bus_number: int = 0
    controller_class: Optional[USBControllerTypes] = None
    ports: List[USBPort] = field(default_factory=list)
    hub_name: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "identifiers": {
                "pci_id": self.pci_id,
                "acpi_path": self.acpi_path,
            },
            "class": str(self.controller_class) if self.controller_class else "Unknown",
            "hub_name": self.hub_name,
            "ports": [p.to_dict() for p in self.ports],
        }


# Linux USB Detection Implementation

class LinuxUSBMap:
    """
    Linux implementation of USB port mapping.
    
    Detects USB controllers and devices using:
    - lspci: PCI device enumeration
    - lsusb: USB device listing  
    - lsusb -t: USB topology tree
    - /sys/bus/usb/devices: Sysfs device information
    """
    
    SYSFS_USB_PATH = Path("/sys/bus/usb/devices")
    
    # Known internal device patterns (vendor:product)
    INTERNAL_DEVICE_PATTERNS = {
        # Intel Bluetooth
        ("8087", "0025"): "Intel Wireless Bluetooth",
        ("8087", "0026"): "Intel Wireless Bluetooth", 
        ("8087", "0029"): "Intel Wireless Bluetooth",
        ("8087", "002a"): "Intel Wireless Bluetooth",
        ("8087", "0032"): "Intel Wireless Bluetooth",
        ("8087", "0033"): "Intel Wireless Bluetooth",
        ("8087", "0aaa"): "Intel Wireless Bluetooth",
        # Realtek Bluetooth
        ("0bda", "b00a"): "Realtek Bluetooth",
        ("0bda", "b00b"): "Realtek Bluetooth",
        ("0bda", "b00c"): "Realtek Bluetooth",
        ("0bda", "8771"): "Realtek Bluetooth",
        # Broadcom Bluetooth
        ("0a5c", "21e6"): "Broadcom Bluetooth",
        ("0a5c", "6412"): "Broadcom Bluetooth",
        # Webcams (common integrated - vendor ID only)
        ("0c45", ""): "Integrated Webcam",  # Sonix
        ("5986", ""): "Integrated Webcam",  # Acer
        ("04f2", ""): "Integrated Webcam",  # Chicony
        ("0408", ""): "Integrated Webcam",  # Quanta
        ("13d3", ""): "Integrated Webcam",  # IMC Networks
        # Fingerprint readers
        ("06cb", ""): "Fingerprint Reader",  # Synaptics
        ("138a", ""): "Fingerprint Reader",  # Validity
        ("27c6", ""): "Fingerprint Reader",  # Goodix
        # Card readers
        ("0bda", "0129"): "Card Reader",  # Realtek
        ("0bda", "0139"): "Card Reader",  # Realtek
    }
    
    def __init__(self):
        self.sysfs_devices: Dict[str, Dict] = {}
        self.lsusb_devices: List[Dict] = []
        self.usb_tree: Dict = {}
        self.controllers: List[Dict] = []
        self.controllers_historical: List[Dict] = []
    
    # =========================================================================
    # Command Execution Helpers
    # =========================================================================
    
    def _run_command(self, cmd: List[str], timeout: int = 10) -> Optional[str]:
        """Execute a shell command and return stdout."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None
    
    # =========================================================================
    # USB Controller Detection (lspci)
    # =========================================================================
    
    def _parse_lspci_output(self) -> List[Dict]:
        """Parse lspci output to find USB controllers."""
        controllers = []
        
        # Get detailed lspci output with numeric IDs
        output = self._run_command(["lspci", "-nnvv"])
        if not output:
            output = self._run_command(["lspci", "-nn"])
            if not output:
                return controllers
        
        current_device = {}
        for line in output.split('\n'):
            if not line.strip():
                if current_device and 'usb' in current_device.get('class_name', '').lower():
                    controllers.append(current_device)
                current_device = {}
                continue
            
            # Device header: "00:14.0 USB controller [0c03]: Intel Corporation..."
            header_match = re.match(
                r'^([0-9a-f:.]+)\s+(.+?)\s+\[([0-9a-f]+)\]:\s+(.+?)\s+\[([0-9a-f]+):([0-9a-f]+)\]',
                line, re.IGNORECASE
            )
            if header_match:
                current_device = {
                    'bdf': header_match.group(1),
                    'class_name': header_match.group(2),
                    'class_id': header_match.group(3),
                    'name': header_match.group(4),
                    'vendor_id': header_match.group(5),
                    'device_id': header_match.group(6),
                }
                continue
            
            # Subsystem line
            subsys_match = re.match(
                r'^\s+Subsystem:\s+.+?\s+\[([0-9a-f]+):([0-9a-f]+)\]',
                line, re.IGNORECASE
            )
            if subsys_match and current_device:
                current_device['subsys_vendor'] = subsys_match.group(1)
                current_device['subsys_device'] = subsys_match.group(2)
                continue
            
            # ProgIf for controller type
            progif_match = re.match(r'^\s+Prog-?If:\s+([0-9a-f]+)', line, re.IGNORECASE)
            if progif_match and current_device:
                current_device['prog_if'] = int(progif_match.group(1), 16)
        
        if current_device and 'usb' in current_device.get('class_name', '').lower():
            controllers.append(current_device)
        
        return controllers
    
    def _get_controller_type(self, pci_info: Dict) -> USBControllerTypes:
        """Determine USB controller type from PCI programming interface."""
        prog_if = pci_info.get('prog_if', 0)
        name_lower = pci_info.get('name', '').lower()
        
        # Check programming interface first (most reliable)
        if prog_if == 0x30:
            return USBControllerTypes.XHCI
        elif prog_if == 0x20:
            return USBControllerTypes.EHCI
        elif prog_if == 0x10:
            return USBControllerTypes.OHCI
        elif prog_if == 0x00 and prog_if != 0:
            return USBControllerTypes.UHCI
        
        # Fallback to name matching (for when lspci -nnvv not available)
        # Check for USB 3.x indicators (XHCI)
        if any(x in name_lower for x in ['xhci', 'usb3', 'usb 3', '3.0', '3.1', '3.2']):
            return USBControllerTypes.XHCI
        # Check for USB 2.x indicators (EHCI)
        elif any(x in name_lower for x in ['ehci', 'usb2', 'usb 2', '2.0']):
            return USBControllerTypes.EHCI
        elif 'ohci' in name_lower:
            return USBControllerTypes.OHCI
        elif 'uhci' in name_lower:
            return USBControllerTypes.UHCI
        
        # If name contains "USB" but we couldn't determine type, assume XHCI for modern systems
        if 'usb' in name_lower:
            return USBControllerTypes.XHCI
        
        return USBControllerTypes.Unknown
    
    # =========================================================================
    # USB Device Detection (lsusb)
    # =========================================================================
    
    def _parse_lsusb_output(self) -> List[Dict]:
        """Parse lsusb output to list all USB devices."""
        devices = []
        
        output = self._run_command(["lsusb"])
        if not output:
            return devices
        
        for line in output.strip().split('\n'):
            # Format: "Bus 001 Device 002: ID 8087:0029 Intel Corp. ..."
            match = re.match(
                r'Bus\s+(\d+)\s+Device\s+(\d+):\s+ID\s+([0-9a-f]+):([0-9a-f]+)\s*(.*)',
                line, re.IGNORECASE
            )
            if match:
                devices.append({
                    'bus': int(match.group(1)),
                    'device': int(match.group(2)),
                    'vendor_id': match.group(3),
                    'product_id': match.group(4),
                    'name': match.group(5).strip() or "Unknown Device",
                })
        
        return devices
    
    def _parse_lsusb_tree(self) -> Dict:
        """Parse lsusb -t output for USB topology tree."""
        tree = {}
        
        output = self._run_command(["lsusb", "-t"])
        if not output:
            return tree
        
        current_bus = None
        
        for line in output.split('\n'):
            if not line.strip():
                continue
            
            # Root hub: "/:  Bus 01.Port 1: Dev 1, Class=root_hub, Driver=xhci_hcd/12p, 480M"
            root_match = re.match(
                r'^/:\s+Bus\s+(\d+)\.Port\s+(\d+):\s+Dev\s+(\d+),\s+Class=(\w+),\s+Driver=([^,]+),\s+(\S+)',
                line
            )
            if root_match:
                bus_num = int(root_match.group(1))
                tree[bus_num] = {
                    'port': int(root_match.group(2)),
                    'device': int(root_match.group(3)),
                    'class': root_match.group(4),
                    'driver': root_match.group(5),
                    'speed': root_match.group(6),
                    'children': {}
                }
                current_bus = bus_num
                continue
            
            # Device: "    |__ Port 1: Dev 2, If 0, Class=Wireless, Driver=btusb, 12M"
            device_match = re.match(
                r'^(\s+)\|?__\s*Port\s+(\d+):\s+Dev\s+(\d+)',
                line
            )
            if device_match and current_bus is not None:
                port_num = int(device_match.group(2))
                dev_num = int(device_match.group(3))
                
                # Extract speed if present
                speed_match = re.search(r',\s*(\d+[MGT])', line)
                speed = speed_match.group(1) if speed_match else ""
                
                tree[current_bus]['children'][port_num] = {
                    'port': port_num,
                    'device': dev_num,
                    'speed': speed,
                }
        
        return tree
    
    # =========================================================================
    # Sysfs Parsing
    # =========================================================================
    
    def _parse_sysfs_devices(self) -> Dict[str, Dict]:
        """Parse /sys/bus/usb/devices for detailed device information."""
        devices = {}
        
        if not self.SYSFS_USB_PATH.exists():
            return devices
        
        for device_path in self.SYSFS_USB_PATH.iterdir():
            if not device_path.is_symlink():
                continue
            
            device_name = device_path.name
            device_info = {'path': str(device_path.resolve())}
            
            attrs = [
                'idVendor', 'idProduct', 'manufacturer', 'product',
                'speed', 'busnum', 'devnum', 'bDeviceClass', 'devpath'
            ]
            
            for attr in attrs:
                attr_path = device_path / attr
                if attr_path.exists():
                    try:
                        device_info[attr] = attr_path.read_text().strip()
                    except (PermissionError, OSError):
                        pass
            
            # Parse device path to get port number
            port_match = re.match(r'^(\d+)-(\d+)(?:\.(\d+))?', device_name)
            if port_match:
                device_info['bus'] = int(port_match.group(1))
                device_info['port'] = int(port_match.group(2))
                if port_match.group(3):
                    device_info['hub_port'] = int(port_match.group(3))
            
            devices[device_name] = device_info
        
        return devices
    
    def _speed_to_class(self, speed: str) -> USBDeviceSpeeds:
        """Convert sysfs speed string to USBDeviceSpeeds enum."""
        speed_lower = speed.lower()
        if '10000' in speed or ('super' in speed_lower and 'plus' in speed_lower):
            return USBDeviceSpeeds.SuperSpeedPlus
        elif '5000' in speed or 'super' in speed_lower:
            return USBDeviceSpeeds.SuperSpeed
        elif '480' in speed or 'high' in speed_lower:
            return USBDeviceSpeeds.HighSpeed
        elif '12' in speed or 'full' in speed_lower:
            return USBDeviceSpeeds.FullSpeed
        elif '1.5' in speed or 'low' in speed_lower:
            return USBDeviceSpeeds.LowSpeed
        return USBDeviceSpeeds.Unknown
    
    def _is_internal_device(self, vendor_id: str, product_id: str) -> bool:
        """Check if a device is likely internal based on vendor/product ID."""
        vid = vendor_id.lower()
        pid = product_id.lower()
        
        if (vid, pid) in self.INTERNAL_DEVICE_PATTERNS:
            return True
        if (vid, "") in self.INTERNAL_DEVICE_PATTERNS:
            return True
        return False
    
    # =========================================================================
    # Controller and Port Assembly
    # =========================================================================
    
    def get_controllers(self):
        """Main method to detect USB controllers and their ports."""
        print(f"\n{Colors.BLUE}[*] Detecting USB controllers...{Colors.RESET}")
        
        pci_controllers = self._parse_lspci_output()
        self.usb_tree = self._parse_lsusb_tree()
        self.lsusb_devices = self._parse_lsusb_output()
        self.sysfs_devices = self._parse_sysfs_devices()
        
        controllers = []
        
        for pci_ctrl in pci_controllers:
            controller = USBController(
                name=pci_ctrl.get('name', 'Unknown USB Controller'),
                pci_id=[
                    pci_ctrl.get('vendor_id', ''),
                    pci_ctrl.get('device_id', ''),
                    pci_ctrl.get('subsys_vendor', ''),
                    pci_ctrl.get('subsys_device', ''),
                ],
                controller_class=self._get_controller_type(pci_ctrl),
            )
            controllers.append(controller)
        
        self._populate_ports(controllers)
        self.controllers = [c.to_dict() for c in controllers]
        
        if not self.controllers_historical:
            self.controllers_historical = self.controllers.copy()
        
        print(f"{Colors.GREEN}[+] Found {len(controllers)} USB controller(s){Colors.RESET}")
        
        return self.controllers
    
    def _populate_ports(self, controllers: List[USBController]):
        """Populate port information for each controller."""
        
        # Filter sysfs devices to only include actual device entries (not interface endpoints)
        # Device entries are like "1-2", "3-2.1" but NOT like "1-2:1.0" (interface endpoints)
        devices_by_bus: Dict[int, List[Dict]] = {}
        for name, info in self.sysfs_devices.items():
            # Skip interface endpoints (contain ':')
            if ':' in name:
                continue
            # Skip root hubs (start with 'usb')  
            if name.startswith('usb'):
                continue
            # Must have vendor ID to be a real device
            if not info.get('idVendor'):
                continue
                
            bus = info.get('bus', 0)
            if bus not in devices_by_bus:
                devices_by_bus[bus] = []
            devices_by_bus[bus].append({'sysfs_name': name, **info})
        
        lsusb_by_bus_dev = {(d['bus'], d['device']): d for d in self.lsusb_devices}
        
        bus_num = 1
        for controller in controllers:
            if controller.controller_class == USBControllerTypes.XHCI:
                tree_data = self.usb_tree.get(bus_num, {})
                driver = tree_data.get('driver', '')
                port_count_match = re.search(r'/(\d+)p', driver)
                total_ports = int(port_count_match.group(1)) if port_count_match else 10
                
                hs_ports = []
                ss_ports = []
                bus_devices = devices_by_bus.get(bus_num, [])
                
                for port_num in range(1, min(total_ports + 1, 16)):
                    # Find device on this port (not through a hub)
                    port_device = None
                    for dev in bus_devices:
                        if dev.get('port') == port_num and 'hub_port' not in dev:
                            port_device = dev
                            break
                    
                    hs_port = USBPort(
                        index=port_num,
                        name=f"HS{port_num:02d}",
                        port_class=USBDeviceSpeeds.HighSpeed,
                    )
                    
                    ss_port = USBPort(
                        index=port_num,
                        name=f"SS{port_num:02d}",
                        port_class=USBDeviceSpeeds.SuperSpeed,
                        companion_port=port_num,
                    )
                    
                    if port_device:
                        device_speed = self._speed_to_class(port_device.get('speed', ''))
                        bus = port_device.get('bus', 0)
                        devnum = int(port_device.get('devnum', 0))
                        lsusb_info = lsusb_by_bus_dev.get((bus, devnum), {})
                        
                        device_name = (
                            port_device.get('product') or
                            lsusb_info.get('name') or
                            'Unknown Device'
                        )
                        
                        vendor_id = port_device.get('idVendor', lsusb_info.get('vendor_id', ''))
                        product_id = port_device.get('idProduct', lsusb_info.get('product_id', ''))
                        
                        usb_device = USBDevice(
                            name=device_name,
                            vendor_id=vendor_id,
                            product_id=product_id,
                            bus=bus,
                            device=devnum,
                            port=port_num,
                            speed=port_device.get('speed', ''),
                            speed_class=device_speed,
                            instance_id=f"{bus}-{port_num}",
                        )
                        
                        if device_speed in (USBDeviceSpeeds.SuperSpeed, USBDeviceSpeeds.SuperSpeedPlus):
                            ss_port.devices.append(usb_device)
                        else:
                            hs_port.devices.append(usb_device)
                        
                        if self._is_internal_device(vendor_id, product_id):
                            if device_speed >= USBDeviceSpeeds.SuperSpeed:
                                ss_port.is_internal = True
                                ss_port.guessed_type = USBPhysicalPortTypes.Internal
                            else:
                                hs_port.is_internal = True
                                hs_port.guessed_type = USBPhysicalPortTypes.Internal
                    
                    hs_ports.append(hs_port)
                    if port_num <= total_ports // 2 + 1:
                        ss_ports.append(ss_port)
                
                controller.ports = hs_ports + ss_ports
                controller.hub_name = f"usb{bus_num}"
            
            elif controller.controller_class == USBControllerTypes.EHCI:
                for port_num in range(1, 9):
                    port = USBPort(
                        index=port_num,
                        name=f"HP{port_num:02d}",
                        port_class=USBDeviceSpeeds.HighSpeed,
                    )
                    controller.ports.append(port)
                controller.hub_name = f"usb{bus_num}"
            
            bus_num += 1


# Blueprint Generation

def generate_blueprint(usb_map: LinuxUSBMap) -> Dict:
    """Generate a USB mapping blueprint in JSON format."""
    blueprint = {
        "version": "1.0",
        "tool": "USBToolBox-Linux",
        "generated_on": "linux",
        "generated_date": datetime.now().isoformat(),
        "controllers": [],
        "internal_devices": [],
        "warnings": [
            "Port connector types are GUESSES - verify in macOS",
            "Companion port mapping may need adjustment",
            "This is a PREPARATION blueprint, not a final mapping",
            "Final USBPorts.kext must be created in macOS",
        ],
    }
    
    internal_devices = []
    
    for controller in (usb_map.controllers or []):
        ctrl_blueprint = {
            "name": controller.get('name', 'Unknown'),
            "pci_id": controller.get('identifiers', {}).get('pci_id', []),
            "acpi_path": controller.get('identifiers', {}).get('acpi_path', ''),
            "type": controller.get('class', 'Unknown'),
            "ports": [],
        }
        
        for port in controller.get('ports', []):
            port_name = port.get('name', f"Port{port.get('index', 0)}")
            is_ss = port_name.startswith('SS')
            
            if port.get('guessed') == 'Internal':
                port_type = 255
            elif is_ss:
                port_type = 3
            else:
                port_type = 0
            
            port_blueprint = {
                "port_name": port_name,
                "port_number": port.get('index', 0),
                "port_type": port_type,
                "port_type_name": _port_type_to_name(port_type),
                "speed_class": port.get('class', 'Unknown'),
                "connector_type": "unknown",
                "is_internal": port.get('guessed') == 'Internal',
                "companion_port": f"{'HS' if is_ss else 'SS'}{port.get('index', 0):02d}" if port.get('guessed') != 'Internal' else None,
                "devices": [],
            }
            
            for device in port.get('devices', []):
                device_blueprint = {
                    "name": device.get('name', 'Unknown'),
                    "vendor_id": device.get('vendor_id', ''),
                    "product_id": device.get('product_id', ''),
                    "speed": device.get('speed', ''),
                }
                port_blueprint["devices"].append(device_blueprint)
                
                if port.get('guessed') == 'Internal':
                    internal_devices.append({
                        "name": device.get('name', 'Unknown'),
                        "vendor_id": device.get('vendor_id', ''),
                        "product_id": device.get('product_id', ''),
                        "port_name": port_name,
                        "suggested_port_type": 255,
                    })
            
            ctrl_blueprint["ports"].append(port_blueprint)
        
        blueprint["controllers"].append(ctrl_blueprint)
    
    blueprint["internal_devices"] = internal_devices
    return blueprint


def _port_type_to_name(port_type: int) -> str:
    """Convert port type code to human-readable name."""
    type_map = {
        0: "USB2 (Type-A)",
        3: "USB3 (Type-A)",
        8: "Type-C (USB2 only)",
        9: "Type-C (with switch)",
        10: "Type-C (without switch)",
        255: "Internal",
    }
    return type_map.get(port_type, "Unknown")


# OpenCore Configuration Guidance

def generate_opencore_guidance() -> str:
    """Generate OpenCore configuration guidance for temporary USB setup."""
    return """
================================================================================
OPENCORE TEMPORARY USB CONFIGURATION
================================================================================

⚠️  WARNING: These settings are TEMPORARY for initial USB discovery only!

--------------------------------------------------------------------------------
KERNEL > QUIRKS (config.plist)
--------------------------------------------------------------------------------

    <key>Kernel</key>
    <dict>
        <key>Quirks</key>
        <dict>
            <!-- TEMPORARY: Enable for initial USB discovery -->
            <key>XhciPortLimit</key>
            <true/>
        </dict>
    </dict>

⚠️  CRITICAL NOTES:

1. XhciPortLimit is BROKEN in macOS 11.3+ (Big Sur and later)!
   - May cause kernel panics or USB instability
   - Use only if absolutely necessary

2. DO NOT use USBInjectAll.kext - it is deprecated!

3. After creating your final USB map, set XhciPortLimit to FALSE

--------------------------------------------------------------------------------
REQUIRED KEXTS
--------------------------------------------------------------------------------

Option A - USBToolBox Method:
  - USBToolBox.kext (from github.com/USBToolBox/kext)
  - UTBMap.kext (your custom port map)

Option B - Native Apple Method:
  - USBPorts.kext (created via Hackintool)
  - No additional kexts required

================================================================================
"""

# Display Functions

def print_topology_report(usb_map: LinuxUSBMap):
    """Print a human-readable USB topology report."""
    print("\n" + "=" * 70)
    print("USB TOPOLOGY REPORT")
    print("=" * 70)
    
    if not usb_map.controllers:
        print(f"\n{Colors.RED}No USB controllers detected!{Colors.RESET}")
        print("Make sure lspci and lsusb are installed.")
        return
    
    for controller in usb_map.controllers:
        ctrl_class = controller.get('class', 'Unknown')
        name = controller.get('name', 'Unknown Controller')
        pci_id = controller.get('identifiers', {}).get('pci_id', [])
        pci_str = ':'.join(pci_id[:2]) if len(pci_id) >= 2 else 'unknown'
        
        print(f"\n{Colors.BLUE}{'─' * 68}{Colors.RESET}")
        print(f"{Colors.GREEN}[{ctrl_class}] {name} ({pci_str}){Colors.RESET}")
        print(f"{Colors.BLUE}{'─' * 68}{Colors.RESET}")
        
        ports = controller.get('ports', [])
        hs_ports = [p for p in ports if p.get('name', '').startswith('HS')]
        ss_ports = [p for p in ports if p.get('name', '').startswith('SS')]
        
        if hs_ports:
            print(f"\n  {Colors.YELLOW}High-Speed (USB 2.0) Ports:{Colors.RESET}")
            for port in sorted(hs_ports, key=lambda x: x.get('index', 0)):
                _print_port(port)
        
        if ss_ports:
            print(f"\n  {Colors.YELLOW}SuperSpeed (USB 3.0) Ports:{Colors.RESET}")
            for port in sorted(ss_ports, key=lambda x: x.get('index', 0)):
                _print_port(port)
    
    print("\n" + "=" * 70)


def _print_port(port: Dict):
    """Print a single port with its devices."""
    name = port.get('name', f"Port {port.get('index', '?')}")
    guessed = port.get('guessed', '')
    devices = port.get('devices', [])
    
    status = ""
    if guessed == 'Internal':
        status = f"{Colors.BLUE}[INTERNAL]{Colors.RESET}"
    elif devices:
        status = f"{Colors.GREEN}[DEVICE]{Colors.RESET}"
    
    print(f"    {name} {status}")
    
    for device in devices:
        device_name = device.get('name', 'Unknown Device')
        vendor = device.get('vendor_id', '????')
        product = device.get('product_id', '????')
        print(f"      └─ {device_name} [{vendor}:{product}]")


# Main Entry Point

def main():
    """Main entry point for Linux USB mapping tool."""
    print(f"\n{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.GREEN}  USBToolBox - Linux USB Port Mapper{Colors.RESET}")
    print(f"{Colors.GREEN}  For Hackintosh USB Preparation{Colors.RESET}")
    print(f"{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    
    print(f"\n{Colors.YELLOW}⚠️  IMPORTANT LIMITATIONS:{Colors.RESET}")
    print("  • This tool creates a PREPARATION blueprint only")
    print("  • Final USB mapping must be completed in macOS")
    print("  • Port connector types cannot be detected on Linux")
    
    usb_map = LinuxUSBMap()
    
    while True:
        print(f"\n{Colors.BLUE}{'─' * 40}{Colors.RESET}")
        print("  D. Discover/Refresh USB Ports")
        print("  S. Show USB Topology Report")
        print("  B. Generate USB Blueprint (JSON)")
        print("  O. Show OpenCore Guidance")
        print("  Q. Quit")
        print(f"{Colors.BLUE}{'─' * 40}{Colors.RESET}")
        
        choice = input("\nSelect option: ").strip().upper()
        
        if choice == 'D':
            usb_map.get_controllers()
            print_topology_report(usb_map)
            
        elif choice == 'S':
            if not usb_map.controllers:
                print(f"\n{Colors.YELLOW}No data yet. Running discovery...{Colors.RESET}")
                usb_map.get_controllers()
            print_topology_report(usb_map)
            
        elif choice == 'B':
            if not usb_map.controllers:
                print(f"\n{Colors.YELLOW}No data yet. Running discovery...{Colors.RESET}")
                usb_map.get_controllers()
            
            blueprint = generate_blueprint(usb_map)
            
            output_path = Path("usb_blueprint.json")
            with open(output_path, 'w') as f:
                json.dump(blueprint, f, indent=2)
            
            print(f"\n{Colors.GREEN}✓ Blueprint saved to: {output_path.absolute()}{Colors.RESET}")
            print(f"\n{Colors.YELLOW}Summary:{Colors.RESET}")
            print(f"  Controllers: {len(blueprint['controllers'])}")
            total_ports = sum(len(c['ports']) for c in blueprint['controllers'])
            print(f"  Total Ports: {total_ports}")
            print(f"  Internal Devices: {len(blueprint['internal_devices'])}")
            
        elif choice == 'O':
            print(generate_opencore_guidance())
            
        elif choice == 'Q':
            print(f"\n{Colors.GREEN}Goodbye!{Colors.RESET}\n")
            break
            
        else:
            print(f"\n{Colors.RED}Invalid option.{Colors.RESET}")


if __name__ == "__main__":
    main()
