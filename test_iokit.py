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
    assert iokit.io_name_t_to_str(name) == "J413AP"

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
