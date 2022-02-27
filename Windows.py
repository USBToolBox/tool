import copy
import json
import time
from enum import Enum

try:
    import wmi  # pylint: disable=import-error
except Exception:  # pylint: disable=broad-except
    # Dummy WMI
    class wmi:  # pylint: disable=invalid-name
        class WMI:
            @staticmethod
            def query(*args, **kwargs):  # pylint: disable=unused-argument
                return []


from base import BaseUSBMap
from Scripts import shared, usbdump


class PnpDeviceProperties(Enum):
    ACPI_PATH = "DEVPKEY_Device_BiosDeviceName"
    DRIVER_KEY = "DEVPKEY_Device_Driver"
    LOCATION_PATHS = "DEVPKEY_Device_LocationPaths"
    FRIENDLY_NAME = "DEVPKEY_Device_FriendlyName"
    BUS_DEVICE_FUNCTION = "DEVPKEY_Device_LocationInfo"
    BUS_REPORTED_NAME = "DEVPKEY_Device_BusReportedDeviceDesc"
    BUS_RELATIONS = "DEVPKEY_Device_BusRelations"
    INTERFACE = "DEVPKEY_PciDevice_ProgIf"
    SERVICE = "DEVPKEY_Device_Service"


class WindowsUSBMap(BaseUSBMap):
    def __init__(self):
        self.usbdump = None
        if shared.test_mode:
            self.wmi = {}
            self.wmi_cache: dict = {p["DEVPKEY_Device_InstanceId"]: p for p in json.load(shared.debug_dump_path.open())["wmitest"] if "duration" not in p}
        else:
            self.wmi = wmi.WMI()
            self.wmi_cache = {}
        self.wmi_retries = {}
        super().__init__()

    def update_usbdump(self):
        self.usbdump = usbdump.get_controllers()

    def get_property_from_wmi(self, instance_id, prop: PnpDeviceProperties):
        MAX_TRIES = 2
        result = None
        if self.wmi_cache.get(instance_id, {}).get(prop.value):
            return self.wmi_cache[instance_id][prop.value]
        elif self.wmi_retries.get(instance_id, {}).get(prop.value, 0) >= MAX_TRIES:
            return None

        try:
            result = self.wmi.query(f"SELECT * FROM Win32_PnPEntity WHERE PNPDeviceID = '{instance_id}'")[0].GetDeviceProperties([prop.value])[0][0].Data
        except IndexError:
            # Race condition between unplug detected in usbdump and WMI
            return None
        except AttributeError:
            if not self.wmi_retries.get(instance_id):
                self.wmi_retries[instance_id] = {prop.value: 1}
            elif not self.wmi_retries[instance_id].get(prop.value):
                self.wmi_retries[instance_id][prop.value] = 1
            else:
                self.wmi_retries[instance_id][prop.value] += 1

            return None

        if not self.wmi_cache.get(instance_id):
            self.wmi_cache[instance_id] = {prop.value: result}
        else:
            self.wmi_cache[instance_id][prop.value] = result

        return result

    """ def get_property_from_wmi(self, instance_id, prop: PnpDeviceProperties):
        value = self.wmi.setdefault(instance_id, {}).get(prop.value)
        if value:
            return value
        else:
            value = input(f"Enter value for {instance_id} {prop}: ")
            self.wmi[instance_id][prop.value] = value
            json.dump(self.wmi, self.wmi_path.open("w"), indent=4, sort_keys=True)
            return value """

    def get_name_from_wmi(self, device):
        if not isinstance(device, dict):
            return
        if device.get("error") or not device["instance_id"]:
            return
        device["name"] = self.get_property_from_wmi(device["instance_id"], PnpDeviceProperties.BUS_REPORTED_NAME) or device["name"]
        for i in device["devices"]:
            self.get_name_from_wmi(i)

    def get_controller_class(self, controller):
        interface = self.get_property_from_wmi(controller["identifiers"]["instance_id"], PnpDeviceProperties.INTERFACE)
        if interface:
            return shared.USBControllerTypes(interface)
        service = self.get_property_from_wmi(controller["identifiers"]["instance_id"], PnpDeviceProperties.SERVICE)
        if not isinstance(service, str):
            shared.debug(f"Unknown controller type for interface {interface} and service {service}!")
            return shared.USBControllerTypes.Unknown
        if service.lower() == "usbxhci":
            return shared.USBControllerTypes.XHCI
        elif service.lower() == "usbehci":
            return shared.USBControllerTypes.EHCI
        elif service.lower() == "usbohci":
            return shared.USBControllerTypes.OHCI
        elif service.lower() == "usbuhci":
            return shared.USBControllerTypes.UHCI
        else:
            shared.debug(f"Unknown controller type for interface {interface} and service {service}!")
            return shared.USBControllerTypes.Unknown

    def get_controllers(self):
        # self.update_usbdump()
        for i in range(10):
            try:
                # time_it(self.update_usbdump, "USBdump time")
                self.update_usbdump()
                break
            except Exception as e:
                if i == 9:
                    raise
                else:
                    shared.debug(e)
                    time.sleep(0.05 if shared.debugging else 2)

        controllers = self.usbdump

        for controller in controllers:
            controller["name"] = self.get_property_from_wmi(controller["identifiers"]["instance_id"], PnpDeviceProperties.FRIENDLY_NAME) or controller["name"]
            controller["class"] = self.get_controller_class(controller)
            acpi_path = self.get_property_from_wmi(controller["identifiers"]["instance_id"], PnpDeviceProperties.ACPI_PATH)
            if acpi_path:
                controller["identifiers"]["acpi_path"] = acpi_path
            driver_key = self.get_property_from_wmi(controller["identifiers"]["instance_id"], PnpDeviceProperties.DRIVER_KEY)
            if driver_key:
                controller["identifiers"]["driver_key"] = driver_key
            location_paths = self.get_property_from_wmi(controller["identifiers"]["instance_id"], PnpDeviceProperties.LOCATION_PATHS)
            if location_paths:
                controller["identifiers"]["location_paths"] = location_paths
            # controller["identifiers"]["bdf"] = self.get_property_from_wmi(controller["identifiers"]["instance_id"], PnpDeviceProperties.BUS_DEVICE_FUNCTION)
            for port in controller["ports"]:
                for device in port["devices"]:
                    self.get_name_from_wmi(device)

        self.controllers = controllers
        if not self.controllers_historical:
            self.controllers_historical = copy.deepcopy(self.controllers)
        else:
            self.merge_controllers(self.controllers_historical, self.controllers)

    def update_devices(self):
        self.get_controllers()


e = WindowsUSBMap()
