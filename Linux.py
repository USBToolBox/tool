import copy
import os
import re
from pathlib import Path
from operator import itemgetter

from base import BaseUSBMap
from Scripts import shared


class LinuxUSBMap(BaseUSBMap):
    def __init__(self):
        super().__init__()

    @staticmethod
    def read_sysfs_file(path):
        """Read a sysfs file and return its contents, or None if it doesn't exist."""
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except (IOError, OSError):
            return None

    @staticmethod
    def get_port_class_from_controller(controller_class):
        """Determine port class fallback based on controller type when version info unavailable."""
        # For EHCI controllers, all ports are USB 2.0 (HighSpeed)
        if controller_class == shared.USBControllerTypes.EHCI:
            return shared.USBDeviceSpeeds.HighSpeed
        # For OHCI/UHCI controllers, all ports are USB 1.1 (FullSpeed)
        elif controller_class in [shared.USBControllerTypes.OHCI, shared.USBControllerTypes.UHCI]:
            return shared.USBDeviceSpeeds.FullSpeed
        # For XHCI controllers without version info, default to HighSpeed (USB 2.0)
        elif controller_class == shared.USBControllerTypes.XHCI:
            return shared.USBDeviceSpeeds.HighSpeed
        else:
            return shared.USBDeviceSpeeds.Unknown

    @staticmethod
    def get_controller_type_from_class(class_code):
        """Determine USB controller type from PCI class code."""
        # USB controller class codes:
        # 0x0C0300 = UHCI
        # 0x0C0310 = OHCI
        # 0x0C0320 = EHCI
        # 0x0C0330 = XHCI
        if not class_code:
            return shared.USBControllerTypes.Unknown
        
        # Remove '0x' prefix if present and get last 2 digits
        class_code = class_code.replace('0x', '')
        if len(class_code) >= 2:
            prog_if = class_code[-2:]
            if prog_if == '00':
                return shared.USBControllerTypes.UHCI
            elif prog_if == '10':
                return shared.USBControllerTypes.OHCI
            elif prog_if == '20':
                return shared.USBControllerTypes.EHCI
            elif prog_if == '30':
                return shared.USBControllerTypes.XHCI
        
        return shared.USBControllerTypes.Unknown

    @staticmethod
    def get_port_speed_class(speed):
        """Convert Linux speed value to USBDeviceSpeeds enum."""
        # Linux speed values:
        # 1.5 = Low Speed
        # 12 = Full Speed
        # 480 = High Speed
        # 5000 = SuperSpeed
        # 10000 = SuperSpeed+
        if not speed:
            return shared.USBDeviceSpeeds.Unknown
        
        try:
            speed_val = float(speed)
            if speed_val <= 1.5:
                return shared.USBDeviceSpeeds.LowSpeed
            elif speed_val <= 12:
                return shared.USBDeviceSpeeds.FullSpeed
            elif speed_val <= 480:
                return shared.USBDeviceSpeeds.HighSpeed
            elif speed_val <= 5000:
                return shared.USBDeviceSpeeds.SuperSpeed
            else:
                return shared.USBDeviceSpeeds.SuperSpeedPlus
        except (ValueError, TypeError):
            return shared.USBDeviceSpeeds.Unknown

    def get_usb_devices_info(self, bus_num):
        """Get information about USB devices on a specific bus."""
        devices = []
        usb_devices_path = Path("/sys/bus/usb/devices")
        
        if not usb_devices_path.exists():
            return devices
        
        # Find all devices on this bus
        for device_path in usb_devices_path.iterdir():
            if not device_path.is_symlink():
                continue
            
            device_name = device_path.name
            # USB device naming: busnum-port.port.port...
            # Root hubs are named: usbN where N is the bus number
            if device_name.startswith(f'usb{bus_num}'):
                continue  # Skip root hub
            
            if not device_name.startswith(f'{bus_num}-'):
                continue  # Not on this bus
            
            # Get device info
            real_path = device_path.resolve()
            product_name = self.read_sysfs_file(real_path / "product")
            manufacturer = self.read_sysfs_file(real_path / "manufacturer")
            speed = self.read_sysfs_file(real_path / "speed")
            
            device_info = {
                "name": product_name or manufacturer or device_name,
                "speed": self.get_port_speed_class(speed),
                "devices": []
            }
            
            devices.append(device_info)
        
        return devices

    def get_controllers(self):
        """Discover USB controllers on the system."""
        controllers = []
        
        # Check if USB sysfs exists
        usb_devices_path = Path("/sys/bus/usb/devices")
        if not usb_devices_path.exists():
            shared.debug("USB sysfs not found, no USB controllers detected")
            self.controllers = controllers
            if not self.controllers_historical:
                self.controllers_historical = copy.deepcopy(self.controllers)
            return
        
        # Find USB root hubs (which correspond to controllers)
        for device_path in sorted(usb_devices_path.iterdir()):
            if not device_path.is_symlink():
                continue
            
            device_name = device_path.name
            # Root hubs are named usbN where N is the bus number
            if not device_name.startswith('usb'):
                continue
            
            try:
                bus_num = int(device_name[3:])
            except ValueError:
                continue
            
            real_path = device_path.resolve()
            
            # Get controller information
            product = self.read_sysfs_file(real_path / "product")
            manufacturer = self.read_sysfs_file(real_path / "manufacturer")
            busnum = self.read_sysfs_file(real_path / "busnum")
            
            # Try to get PCI information by walking up the device tree
            pci_path = None
            current_path = real_path
            while current_path != current_path.parent:
                if (current_path / "vendor").exists() and (current_path / "device").exists():
                    pci_path = current_path
                    break
                current_path = current_path.parent
            
            # Build controller info
            controller_name = product or f"USB Controller (Bus {bus_num})"
            
            identifiers = {}
            identifiers["bus_number"] = bus_num
            
            # Get PCI IDs if available
            if pci_path:
                vendor = self.read_sysfs_file(pci_path / "vendor")
                device = self.read_sysfs_file(pci_path / "device")
                subsystem_vendor = self.read_sysfs_file(pci_path / "subsystem_vendor")
                subsystem_device = self.read_sysfs_file(pci_path / "subsystem_device")
                
                pci_id = []
                if vendor:
                    pci_id.append(vendor.replace('0x', ''))
                if device:
                    pci_id.append(device.replace('0x', ''))
                if subsystem_vendor:
                    pci_id.append(subsystem_vendor.replace('0x', ''))
                if subsystem_device:
                    pci_id.append(subsystem_device.replace('0x', ''))
                
                if pci_id:
                    identifiers["pci_id"] = pci_id
                
                # Get PCI class code to determine controller type
                class_code = self.read_sysfs_file(pci_path / "class")
                controller_class = self.get_controller_type_from_class(class_code)
                
                # Get BDF (Bus:Device:Function)
                pci_addr = pci_path.name
                bdf_match = re.match(r'([0-9a-f]{4}):([0-9a-f]{2}):([0-9a-f]{2})\.([0-9a-f])', pci_addr)
                if bdf_match:
                    identifiers["bdf"] = [
                        int(bdf_match.group(2), 16),  # Bus
                        int(bdf_match.group(3), 16),  # Device
                        int(bdf_match.group(4), 16)   # Function
                    ]
            else:
                controller_class = shared.USBControllerTypes.Unknown
            
            # Get maxchild (number of ports)
            maxchild = self.read_sysfs_file(real_path / "maxchild")
            try:
                num_ports = int(maxchild) if maxchild else 0
            except ValueError:
                num_ports = 0
            
            # Get USB version from root hub to determine port capabilities
            version = self.read_sysfs_file(real_path / "version")
            
            # Determine port class based on root hub version
            # XHCI controllers create separate USB 2.0 and USB 3.0 root hubs
            default_port_class = shared.USBDeviceSpeeds.Unknown
            if version:
                if version.startswith("3."):
                    # USB 3.x root hub - ports are SuperSpeed capable
                    default_port_class = shared.USBDeviceSpeeds.SuperSpeed
                elif version.startswith("2."):
                    # USB 2.x root hub - ports are HighSpeed capable
                    default_port_class = shared.USBDeviceSpeeds.HighSpeed
                elif version.startswith("1."):
                    # USB 1.x root hub - ports are FullSpeed capable
                    default_port_class = shared.USBDeviceSpeeds.FullSpeed
            
            # Fall back to controller type if version not available
            if default_port_class == shared.USBDeviceSpeeds.Unknown:
                default_port_class = self.get_port_class_from_controller(controller_class)
            
            # Build port list
            ports = []
            for port_num in range(1, num_ports + 1):
                # Guess connector type based on port class
                # Since Linux doesn't expose detailed connector info, we use reasonable defaults
                guessed_type = None
                if default_port_class == shared.USBDeviceSpeeds.SuperSpeed:
                    # USB 3.0 ports - most commonly USB 3 Type A
                    guessed_type = shared.USBPhysicalPortTypes.USB3TypeA
                elif default_port_class == shared.USBDeviceSpeeds.HighSpeed:
                    # USB 2.0 ports - most commonly USB Type A
                    guessed_type = shared.USBPhysicalPortTypes.USBTypeA
                elif default_port_class == shared.USBDeviceSpeeds.FullSpeed:
                    # USB 1.1 ports - most commonly USB Type A
                    guessed_type = shared.USBPhysicalPortTypes.USBTypeA
                
                port = {
                    "name": f"Port {port_num}",
                    "comment": None,
                    "index": port_num,
                    "class": default_port_class,
                    "type": None,
                    "guessed": guessed_type,
                    "devices": []
                }
                ports.append(port)
            
            controller = {
                "name": controller_name,
                "class": controller_class,
                "identifiers": identifiers,
                "ports": ports
            }
            
            controllers.append(controller)
        
        self.controllers = controllers
        if not self.controllers_historical:
            self.controllers_historical = copy.deepcopy(self.controllers)
        else:
            self.merge_controllers(self.controllers_historical, self.controllers)
        
        self.update_devices()

    def update_devices(self):
        """Update device information for all controllers."""
        if not self.controllers:
            return
        
        usb_devices_path = Path("/sys/bus/usb/devices")
        if not usb_devices_path.exists():
            return
        
        for controller in self.controllers:
            bus_num = controller["identifiers"].get("bus_number")
            if not bus_num:
                continue
            
            # Find devices connected to this controller
            for device_path in usb_devices_path.iterdir():
                if not device_path.is_symlink():
                    continue
                
                device_name = device_path.name
                
                # Skip root hub
                if device_name.startswith(f'usb{bus_num}'):
                    continue
                
                # Check if device is on this bus and get port number
                # Format: busnum-port or busnum-port.subport.subport...
                if device_name.startswith(f'{bus_num}-'):
                    port_info = device_name[len(f'{bus_num}-'):]
                    # Get the first port number (before any dots)
                    port_num_str = port_info.split('.')[0].split(':')[0]
                    try:
                        port_num = int(port_num_str)
                    except ValueError:
                        continue
                    
                    # Find the corresponding port in our controller
                    matching_ports = [p for p in controller["ports"] if p["index"] == port_num]
                    if not matching_ports:
                        continue
                    
                    port = matching_ports[0]
                    
                    # Get device information
                    real_path = device_path.resolve()
                    product = self.read_sysfs_file(real_path / "product")
                    manufacturer = self.read_sysfs_file(real_path / "manufacturer")
                    speed = self.read_sysfs_file(real_path / "speed")
                    
                    device_info = {
                        "name": product or manufacturer or device_name,
                        "speed": self.get_port_speed_class(speed),
                        "devices": []
                    }
                    
                    # Update port class based on device speed (skip Unknown values)
                    if device_info["speed"] != shared.USBDeviceSpeeds.Unknown:
                        if port["class"] == shared.USBDeviceSpeeds.Unknown or device_info["speed"] > port["class"]:
                            port["class"] = device_info["speed"]
                    
                    # Check if device already exists in port (avoid duplicates)
                    existing_device_names = [d.get("name") for d in port["devices"] if isinstance(d, dict)]
                    if device_info["name"] not in existing_device_names:
                        port["devices"].append(device_info)
        
        if self.controllers_historical:
            self.merge_devices(self.controllers_historical, self.controllers)


e = LinuxUSBMap()
