import subprocess

from Scripts import iokit


def _get_IOResources():
    matching = iokit.IOServiceMatching("IOResources".encode())

    err, iterator = iokit.IOServiceGetMatchingServices(iokit.kIOMasterPortDefault, matching, None)
    assert err == 0
    assert iterator is not None

    results = list(iokit.ioiterator_to_list(iterator))
    assert len(results) == 1
    return results[0]


def test_IOServiceMatching():
    matching = iokit.IOServiceMatching("IOResources".encode())
    assert iokit.corefoundation_to_native(matching) == {
        "IOProviderClass": "IOResources",
    }


def test_IOServiceNameMatching():
    matching = iokit.IOServiceNameMatching("IOResources".encode())
    assert iokit.corefoundation_to_native(matching) == {"IONameMatch": "IOResources"}


def test_IOServiceGetMatchingServices():
    err = iokit.IOObjectRelease(_get_IOResources())
    assert err == 0


def test_IORegistryEntryCreateCFProperty():
    device = _get_IOResources()
    cf_property = iokit.IORegistryEntryCreateCFProperty(device, "IOKit", iokit.kCFAllocatorDefault, 0)

    result = iokit.corefoundation_to_native(cf_property)
    assert isinstance(result, str)
    assert len(result) > 0

    err = iokit.IOObjectRelease(device)
    assert err == 0


def test_IORegistryEntryCreateCFProperties():
    device = _get_IOResources()
    err, cf_properties = iokit.IORegistryEntryCreateCFProperties(device, None, iokit.kCFAllocatorDefault, 0)
    assert err == 0

    result = iokit.corefoundation_to_native(cf_properties)
    assert isinstance(result, dict)
    assert len(result) > 0
    assert result["IOKit"] == "IOService"

    err = iokit.IOObjectRelease(device)
    assert err == 0


def test_IORegistryEntrySearchCFProperty():
    device = _get_IOResources()

    cf_property = iokit.IORegistryEntrySearchCFProperty(
        device,
        "IOService".encode(),
        "IOPlatformSerialNumber",
        iokit.CFAllocatorRef.kCFAllocatorDefault,
        iokit.kIORegistryIterateRecursively | iokit.kIORegistryIterateParents,
    )

    result = iokit.corefoundation_to_native(cf_property)
    assert isinstance(result, str)
    assert len(result) > 0

    err = iokit.IOObjectRelease(device)
    assert err == 0


def test_IORegistryEntryGetParentEntry():
    device = _get_IOResources()

    err, parent = iokit.IORegistryEntryGetParentEntry(device, "IOService".encode(), None)
    assert err == 0
    assert parent is not None

    err, name = iokit.IORegistryEntryGetName(parent, None)
    assert err == 0
    assert iokit.io_name_t_to_str(name) == subprocess.check_output(["sysctl", "hw.model"]).decode().split(": ")[1].replace("\n", "").strip()

    err = iokit.IOObjectRelease(device)
    assert err == 0

    err = iokit.IOObjectRelease(parent)
    assert err == 0


def test_IORegistryEntryGetName():
    device = _get_IOResources()

    err, name = iokit.IORegistryEntryGetName(device, None)
    assert err == 0
    assert iokit.io_name_t_to_str(name) == "IOResources"

    err = iokit.IOObjectRelease(device)
    assert err == 0


def test_IOObjectRelease():
    err, iterator = iokit.IORegistryCreateIterator(iokit.kIOMainPortDefault, "IOService".encode(), iokit.kNilOptions, None)
    assert err == 0

    err = iokit.IOObjectRelease(iterator)
    assert err == 0


def test_IOObjectConformsTo():
    device = _get_IOResources()

    assert iokit.IOObjectConformsTo(device, "IOResources".encode()) == True


def test_IOObjectGetClass():
    device = _get_IOResources()

    err, class_name = iokit.IOObjectGetClass(device, None)
    assert err == 0
    assert iokit.io_name_t_to_str(class_name) == "IOResources"

    err = iokit.IOObjectRelease(device)
    assert err == 0


def test_IOObjectCopyClass():
    device = _get_IOResources()

    class_name = iokit.corefoundation_to_native(iokit.IOObjectCopyClass(device))
    assert class_name == "IOResources"

    err = iokit.IOObjectRelease(device)
    assert err == 0


def test_IOObjectCopySuperclassForClass():
    class_name = "IOService"
    superclass_name = iokit.corefoundation_to_native(iokit.IOObjectCopySuperclassForClass(class_name))
    assert superclass_name == "IORegistryEntry"


def test_IOIteratorNext():
    err, iterator = iokit.IORegistryCreateIterator(iokit.kIOMainPortDefault, "IOService".encode(), iokit.kNilOptions, None)
    assert err == 0

    obj = iokit.IOIteratorNext(iterator)
    assert obj != 0  # 0 means the iterator handle is invalid

    err = iokit.IOObjectRelease(obj)
    assert err == 0


def test_IOIteratorIsValid():
    err, iterator = iokit.IORegistryCreateIterator(iokit.kIOMainPortDefault, "IOService".encode(), iokit.kNilOptions, None)
    assert err == 0
    assert iokit.IOIteratorIsValid(iterator) == True


def test_IORegistryEntryFromPath():
    device = iokit.IORegistryEntryFromPath(iokit.kIOMainPortDefault, "IOService:/IOResources".encode())
    assert device != iokit.NULL

    err = iokit.IOObjectRelease(device)
    assert err == 0


def test_IORegistryEntryGetLocationInPlane():
    err, matched = iokit.IOServiceGetMatchingServices (
            iokit.kIOMainPortDefault,
            {
                "IOPropertyMatch": [
                    {
                        "processor-number": 0
                    },
                    {
                        "logical-cpu-id": 0
                    }
                ]
            },
            None
        )
    assert err == 0

    iters = list(iokit.ioiterator_to_list(matched))
    err, location = iokit.IORegistryEntryGetLocationInPlane (
            iters[0],
            b"IOService",
            None
        )
    assert err == 0
    assert location.replace(b"\x00", b"") == b"0"


    for i in iters:
        err = iokit.IOObjectRelease(i)
        assert err == 0


def test_IORegistryEntryGetPath():
    device = _get_IOResources()

    err, path = iokit.IORegistryEntryGetPath(device, "IOService".encode(), None)
    assert err == 0
    assert path.replace(b"\x00", b"") == b"IOService:/IOResources"


def test_IORegistryEntryCopyPath():
    device = _get_IOResources()

    path = iokit.IORegistryEntryCopyPath(device, "IOService".encode())
    assert path == "IOService:/IOResources"


def test_IORegistryEntryIDMatching():
    device = iokit.IORegistryEntryIDMatching(4294967578)
    assert iokit.corefoundation_to_native(device) == {"IORegistryEntryID": 4294967578}


def test_IORegistryEntryGetRegistryEntryID():
    device = _get_IOResources()

    err, obj_id = iokit.IORegistryEntryGetRegistryEntryID(device, None)
    assert err == 0
    assert obj_id >= 0


def test_IORegistryEntryGetChildIterator():
    device = _get_IOResources()
    
    err, iterator = iokit.IORegistryEntryGetChildIterator (
            device,
            "IOService".encode(),
            None
        )
    assert err == 0

    err = iokit.IOObjectRelease(iterator)
    assert err == 0

    err = iokit.IOObjectRelease(device)
    assert err == 0


def test_IORegistryCreateIterator():
    err, iterator = iokit.IORegistryCreateIterator (
            iokit.kIOMainPortDefault,
            "IODeviceTree".encode(),
            iokit.kIORegistryIterateRecursively,
            None
        )
    assert err == 0

    interface = list(iokit.ioiterator_to_list(iterator))

    err, props = iokit.IORegistryEntryCreateCFProperties (
            interface[0], None, iokit.kCFAllocatorDefault, iokit.kNilOptions
        )
    assert err == 0
    assert props.get("IOPlatformUUID") != None

    for i in interface:
        err = iokit.IOObjectRelease(i)
        assert err == 0


def test_IORegistryEntryCreateIterator():
    device = _get_IOResources()

    err, iterator = iokit.IORegistryEntryCreateIterator(device, "IOService".encode(), iokit.kIORegistryIterateRecursively, None)
    assert err == 0

    interface = list(iokit.ioiterator_to_list(iterator))

    err, props = iokit.IORegistryEntryCreateCFProperties(interface[0], None, iokit.kCFAllocatorDefault, iokit.kNilOptions)
    assert err == 0
    assert props.get("IOProviderClass") == "IOResources"

    for i in interface:
        err = iokit.IOObjectRelease(i)
        assert err == 0


def test_IORegistryIteratorEnterEntry():
    device = _get_IOResources()

    err, iterator = iokit.IORegistryEntryCreateIterator(device, "IOService".encode(), iokit.kIORegistryIterateRecursively, None)
    assert err == 0

    err = iokit.IORegistryIteratorEnterEntry(iterator)
    assert err == 0


def test_IORegistryIteratorExitEntry():
    device = _get_IOResources()

    err, iterator = iokit.IORegistryCreateIterator(iokit.kIOMainPortDefault, "IOService".encode(), iokit.kNilOptions, None)
    assert err == 0

    rec_lvl = 0
    entry = 0
    while True:
        entry = iokit.IOIteratorNext(entry)

        if entry:
            rec_lvl += 1
            assert iokit.IORegistryIteratorEnterEntry(iter) == 0

        else:
            if rec_lvl == 0:
                break

            rec_lvl -= 1
            assert iokit.IORegistryIteratorExitEntry(iter) == 0


test_IORegistryEntryGetLocationInPlane()