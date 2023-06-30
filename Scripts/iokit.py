import abc
import inspect
import typing
from types import NoneType
from typing import NewType, Union, cast

import CoreFoundation
import objc
from CoreFoundation import CFRelease  # type: ignore # pylint: disable=no-name-in-module
from Foundation import NSBundle  # type: ignore # pylint: disable=no-name-in-module
from PyObjCTools import Conversion

IOKit_bundle = NSBundle.bundleWithIdentifier_("com.apple.framework.IOKit")

USE_TOLL_FREE_BRIDGING = True


class ObjCClass(abc.ABC):
    encoding: bytes


def _type_to_encoding(type_: Union[type, bytes]):
    if inspect.isclass(type_):
        if issubclass(type_, ObjCClass):
            return type_.encoding

        raise TypeError("Type must be an ObjCClass")

    if isinstance(type_, bytes):
        return type_

    raise TypeError("Type must be an ObjCClass or bytes")


def OUT(out_type: Union[type, bytes]):
    return b"o" + _type_to_encoding(out_type)


def POINTER(type_: Union[type, bytes]):
    return b"^" + _type_to_encoding(type_)


def CONST(type_: Union[type, bytes]):
    return b"r" + _type_to_encoding(type_)


class Encodings:
    id = b"@"
    void = b"v"
    bool = b"B"
    unsigned_long = unsigned_long_long = uint64_t = b"Q"
    # For input, we use (const) char* pointers, as we do not need an exactly 128 byte buffer
    char_ptr = b"*"
    io_name_t_in = char_ptr
    # For output, IOKit expects and we provide a 128 byte buffer
    io_name_t_out = b"[128c]"
    io_string_t_in = char_ptr
    io_string_t_out = b"[512c]"

    kern_return_t = b"i"
    mach_port_t = b"I"
    io_object_t = mach_port_t
    io_registry_entry_t = io_object_t
    io_iterator_t = io_object_t

    CFDictionaryRef = b"^{__CFDictionary=}"
    CFMutableDictionaryRef = CFDictionaryRef  # internally, they are the same
    CFAllocatorRef = b"^{__CFAllocator=}"
    IOOptionBits = b"I"


def STRUCT_POINTER(name: str):
    if USE_TOLL_FREE_BRIDGING and name in [
        "__CFArray",
        "__CFBoolean",
        "__CFData",
        "__CFDictionary",
        "__CFMutableArray",
        "__CFMutableData",
        "__CFMutableDictionary",
        "__CFMutableSet",
        "__CFMutableString",
        "__CFNull",
        "__CFNumber",
        "__CFSet",
        "__CFString",
        "__CFURL",
    ]:
        return Encodings.id

    return POINTER(b"{" + name.encode() + b"=}")


# CFDictionaryRef = objc_class_factory("CFDictionaryRef", b"^{__CFDictionary=}")


class CFTypeRef(ObjCClass, abc.ABC):
    # If we use void pointer, we will get an int back, which corefoundation_to_native will fail on
    encoding = Encodings.id


class CFDictionaryRef(CFTypeRef, dict):
    encoding = STRUCT_POINTER("__CFDictionary")


# Separate class as not all dictionaries are mutable
class CFMutableDictionaryRef(CFDictionaryRef):
    pass  # internally, they are the same encoding


class CFAllocatorRef(CFTypeRef):
    encoding = STRUCT_POINTER("__CFAllocator")
    kCFAllocatorDefault: "CFAllocatorRef" = cast(
        "CFAllocatorRef",
        CoreFoundation.kCFAllocatorDefault,  # type: ignore  # pylint: disable=no-member
    )


io_name_t_ref = b"[128c]"  # pylint: disable=invalid-name
const_io_name_t_ref_in = b"r*"

CFStringRef = b"^{__CFString=}"
CFDictionaryRef = b"^{__CFDictionary=}"
# CFAllocatorRef = b"^{__CFAllocator=}"


def gen_encoding(return_type, *arguments):
    return _type_to_encoding(return_type) + b"".join(_type_to_encoding(arg) for arg in arguments)


class Car:
    pass


# https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/ObjCRuntimeGuide/Articles/ocrtTypeEncodings.html
functions = [
    (
        "IORegistryEntryCreateCFProperties",
        gen_encoding(
            Encodings.kern_return_t,
            Encodings.io_registry_entry_t,
            OUT(POINTER(CFMutableDictionaryRef)),
            CFAllocatorRef,
            Encodings.IOOptionBits,
        ),
    ),
    # For some reason, IOServiceMatching declares a const char* instead of an io_name_t
    ("IOServiceMatching", gen_encoding(CFMutableDictionaryRef, CONST(Encodings.char_ptr))),
    (
        "IOServiceGetMatchingServices",
        gen_encoding(Encodings.kern_return_t, Encodings.mach_port_t, CFDictionaryRef, OUT(POINTER(Encodings.io_iterator_t))),
    ),
    ("IOIteratorNext", gen_encoding(Encodings.io_object_t, Encodings.io_iterator_t)),
    (
        "IORegistryEntryGetParentEntry",
        gen_encoding(
            Encodings.kern_return_t,
            Encodings.io_registry_entry_t,
            CONST(Encodings.io_name_t_in),
            OUT(POINTER(Encodings.io_registry_entry_t)),
        ),
    ),
    ("IOObjectRelease", gen_encoding(Encodings.kern_return_t, Encodings.io_object_t)),
    # io_name_t is char[128]
    ("IORegistryEntryGetName", gen_encoding(Encodings.kern_return_t, Encodings.io_registry_entry_t, OUT(Encodings.io_name_t_out))),
    ("IOObjectGetClass", gen_encoding(Encodings.kern_return_t, Encodings.io_object_t, OUT(Encodings.io_name_t_out))),
    ("IOObjectCopyClass", gen_encoding(CFStringRef, Encodings.io_object_t)),
    ("IOObjectCopySuperclassForClass", gen_encoding(CFStringRef, CFStringRef)),
    (
        "IORegistryEntryGetChildIterator",
        gen_encoding(
            Encodings.kern_return_t, Encodings.io_registry_entry_t, CONST(Encodings.io_name_t_in), OUT(POINTER(Encodings.io_iterator_t))
        ),
    ),
    ("IORegistryCreateIterator", b"IIr*Io^I"),
    ("IORegistryEntryCreateIterator", b"IIr*Io^I"),
    ("IORegistryIteratorEnterEntry", b"II"),
    ("IORegistryIteratorExitEntry", b"II"),
    (
        "IORegistryEntryCreateCFProperty",
        gen_encoding(CFTypeRef, Encodings.io_registry_entry_t, CFStringRef, CFAllocatorRef, Encodings.IOOptionBits),
    ),
    (
        "IORegistryEntrySearchCFProperty",
        gen_encoding(CFTypeRef, Encodings.io_registry_entry_t, b"r*", CFStringRef, CFAllocatorRef, Encodings.IOOptionBits),
    ),
    (
        "IORegistryEntryGetPath",
        gen_encoding(Encodings.kern_return_t, Encodings.io_registry_entry_t, CONST(Encodings.io_name_t_in), OUT(Encodings.io_string_t_out)),
    ),
    ("IORegistryEntryCopyPath", gen_encoding(CFStringRef, Encodings.io_registry_entry_t, CONST(Encodings.io_name_t_in))),
    ("IOObjectConformsTo", gen_encoding(Encodings.bool, Encodings.io_object_t, CONST(Encodings.io_name_t_in))),
    (
        "IORegistryEntryGetLocationInPlane",
        gen_encoding(Encodings.kern_return_t, Encodings.io_registry_entry_t, CONST(Encodings.io_name_t_in), OUT(Encodings.io_name_t_out)),
    ),
    ("IOServiceNameMatching", gen_encoding(CFMutableDictionaryRef, CONST(Encodings.char_ptr))),
    ("IORegistryEntryGetRegistryEntryID", gen_encoding(Encodings.kern_return_t, Encodings.io_registry_entry_t, OUT(Encodings.uint64_t))),
    ("IORegistryEntryIDMatching", gen_encoding(CFMutableDictionaryRef, Encodings.uint64_t)),
    ("IORegistryEntryFromPath", gen_encoding(Encodings.io_registry_entry_t, Encodings.mach_port_t, CONST(Encodings.io_string_t_in))),
]

# TODO: Proper typing

# pylint: disable=invalid-name
pointer = NoneType

kern_return_t = NewType("kern_return_t", int)

io_object_t = NewType("io_object_t", object)
io_name_t = bytes
io_string_t = bytes

# io_registry_entry_t = NewType("io_registry_entry_t", io_object_t)
io_registry_entry_t = io_object_t
io_iterator_t = NewType("io_iterator_t", io_object_t)

# CFTypeRef = Union[int, float, bytes, dict, list]

IOOptionBits = int
mach_port_t = int
# CFAllocatorRef = int

NULL = 0

kIOMasterPortDefault: mach_port_t = NULL
kIOMainPortDefault = kIOMasterPortDefault

from CoreFoundation import (
    kCFAllocatorDefault,
)  # type: ignore # pylint: disable=no-name-in-module, ungrouped-imports, wrong-import-position # noqa: E402, F401

# kCFAllocatorDefault: CFAllocatorRef = NULL
kNilOptions: IOOptionBits = NULL

kIORegistryIterateRecursively = 1
kIORegistryIterateParents = 2

# pylint: enable=invalid-name


def bind(func):
    # TODO: Automatically create encodings from the function signature
    print(typing.get_type_hints(func))
    return func


# kern_return_t IORegistryEntryCreateCFProperties(io_registry_entry_t entry, CFMutableDictionaryRef * properties, CFAllocatorRef allocator, IOOptionBits options);
def IORegistryEntryCreateCFProperties(
    entry: io_registry_entry_t, properties: pointer, allocator: CFAllocatorRef, options: IOOptionBits
) -> tuple[kern_return_t, CFMutableDictionaryRef]:  # pylint: disable=invalid-name
    raise NotImplementedError


# CFMutableDictionaryRef IOServiceMatching(const char * name);
@bind
def IOServiceMatching(name: bytes) -> CFMutableDictionaryRef:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IOServiceGetMatchingServices(mach_port_t masterPort, CFDictionaryRef matching CF_RELEASES_ARGUMENT, io_iterator_t * existing);
def IOServiceGetMatchingServices(
    masterPort: mach_port_t, matching: dict, existing: pointer
) -> tuple[kern_return_t, io_iterator_t]:  # pylint: disable=invalid-name
    raise NotImplementedError


# io_object_t IOIteratorNext(io_iterator_t iterator);
def IOIteratorNext(iterator: io_iterator_t) -> io_object_t:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryEntryGetParentEntry(io_registry_entry_t entry, const io_name_t plane, io_registry_entry_t * parent);
def IORegistryEntryGetParentEntry(
    entry: io_registry_entry_t, plane: io_name_t, parent: pointer
) -> tuple[kern_return_t, io_registry_entry_t]:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IOObjectRelease(io_object_t object);
def IOObjectRelease(object: io_object_t) -> kern_return_t:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryEntryGetName(io_registry_entry_t entry, io_name_t name);
def IORegistryEntryGetName(entry: io_registry_entry_t, name: pointer) -> tuple[kern_return_t, bytes]:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IOObjectGetClass(io_object_t object, io_name_t className);
def IOObjectGetClass(object: io_object_t, className: pointer) -> tuple[kern_return_t, bytes]:  # pylint: disable=invalid-name
    raise NotImplementedError


# CFStringRef IOObjectCopyClass(io_object_t object);
def IOObjectCopyClass(object: io_object_t) -> str:  # pylint: disable=invalid-name
    raise NotImplementedError


# CFStringRef IOObjectCopySuperclassForClass(CFStringRef classname)
def IOObjectCopySuperclassForClass(classname: str) -> str:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryEntryGetChildIterator(io_registry_entry_t entry, const io_name_t plane, io_iterator_t * iterator);
def IORegistryEntryGetChildIterator(
    entry: io_registry_entry_t, plane: io_name_t, iterator: pointer
) -> tuple[kern_return_t, io_iterator_t]:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryCreateIterator(mach_port_t masterPort, const io_name_t plane, IOOptionBits options, io_iterator_t * iterator)
def IORegistryCreateIterator(
    masterPort: mach_port_t, plane: io_name_t, options: IOOptionBits, iterator: pointer
) -> tuple[kern_return_t, io_iterator_t]:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryEntryCreateIterator(io_registry_entry_t entry, const io_name_t plane, IOOptionBits options, io_iterator_t * iterator)
def IORegistryEntryCreateIterator(
    entry: io_registry_entry_t, plane: io_name_t, options: IOOptionBits, iterator: pointer
) -> tuple[kern_return_t, io_iterator_t]:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryIteratorEnterEntry(io_iterator_t iterator)
def IORegistryIteratorEnterEntry(iterator: io_iterator_t) -> kern_return_t:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryIteratorExitEntry(io_iterator_t iterator)
def IORegistryIteratorExitEntry(iterator: io_iterator_t) -> kern_return_t:  # pylint: disable=invalid-name
    raise NotImplementedError


# CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t entry, CFStringRef key, CFAllocatorRef allocator, IOOptionBits options);
def IORegistryEntryCreateCFProperty(
    entry: io_registry_entry_t, key: str, allocator: CFAllocatorRef, options: IOOptionBits
) -> CFTypeRef:  # pylint: disable=invalid-name
    raise NotImplementedError


# CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t entry, const io_name_t plane, CFStringRef key, CFAllocatorRef allocator, IOOptionBits options);
def IORegistryEntrySearchCFProperty(
    entry: io_registry_entry_t, plane: io_name_t, key: str, allocator: CFAllocatorRef, options: IOOptionBits
) -> CFTypeRef:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryEntryGetPath(io_registry_entry_t entry, const io_name_t plane, io_string_t path);
def IORegistryEntryGetPath(
    entry: io_registry_entry_t, plane: io_name_t, path: pointer
) -> tuple[kern_return_t, io_string_t]:  # pylint: disable=invalid-name
    raise NotImplementedError


# CFStringRef IORegistryEntryCopyPath(io_registry_entry_t entry, const io_name_t plane)
def IORegistryEntryCopyPath(entry: io_registry_entry_t, plane: bytes) -> str:  # pylint: disable=invalid-name
    raise NotImplementedError


# # boolean_t IOObjectConformsTo(io_object_t object, const io_name_t className)
# def IOObjectConformsTo(object: io_object_t, className: bytes) -> boolean_t:  # pylint: disable=invalid-name
#     raise NotImplementedError


# kern_return_t IORegistryEntryGetLocationInPlane(io_registry_entry_t entry, const io_name_t plane, io_name_t location)
def IORegistryEntryGetLocationInPlane(
    entry: io_registry_entry_t, plane: io_name_t, location: pointer
) -> tuple[kern_return_t, bytes]:  # pylint: disable=invalid-name
    raise NotImplementedError


# CFMutableDictionaryRef IOServiceNameMatching(const char * name);
def IOServiceNameMatching(name: bytes) -> dict:  # pylint: disable=invalid-name
    raise NotImplementedError


# kern_return_t IORegistryEntryGetRegistryEntryID(io_registry_entry_t entry, uint64_t * entryID)
def IORegistryEntryGetRegistryEntryID(
    entry: io_registry_entry_t, entryID: pointer
) -> tuple[kern_return_t, int]:  # pylint: disable=invalid-name
    raise NotImplementedError


# CFMutableDictionaryRef IORegistryEntryIDMatching(uint64_t entryID);
def IORegistryEntryIDMatching(entryID: int) -> dict:  # pylint: disable=invalid-name
    raise NotImplementedError


# io_registry_entry_t IORegistryEntryFromPath(mach_port_t mainPort, const io_string_t path)
def IORegistryEntryFromPath(mainPort: mach_port_t, path: io_string_t) -> io_registry_entry_t:  # pylint: disable=invalid-name
    raise NotImplementedError


objc.loadBundleFunctions(IOKit_bundle, globals(), functions)  # type: ignore # pylint: disable=no-member
# objc.loadBundleVariables(IOKit_bundle, globals(), variables)  # type: ignore # pylint: disable=no-member


def ioiterator_to_list(iterator: io_iterator_t):
    # items = []
    item = IOIteratorNext(iterator)
    while item:
        # items.append(next)
        yield item
        item = IOIteratorNext(iterator)
    IOObjectRelease(iterator)
    # return items


def corefoundation_to_native(collection):
    native = Conversion.pythonCollectionFromPropertyList(collection)
    CFRelease(collection)
    return native


def native_to_corefoundation(native):
    return Conversion.propertyListFromPythonCollection(native)


def io_name_t_to_str(name: bytes):
    return name.partition(b"\0")[0].decode()


def get_class_inheritance(io_object):
    classes = []
    cls = IOObjectCopyClass(io_object)
    while cls:
        # yield cls
        classes.append(cls)
        CFRelease(cls)
        cls = IOObjectCopySuperclassForClass(cls)
    return classes
