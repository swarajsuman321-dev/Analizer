"""Read .lnk targets using IShellLinkW, without WScript's ANSI best-fit paths."""
import ctypes
from pathlib import Path
import uuid


def shortcut_target(filename):
    class GUID(ctypes.Structure):
        _fields_=[('data1',ctypes.c_uint32),('data2',ctypes.c_uint16),
                  ('data3',ctypes.c_uint16),('data4',ctypes.c_ubyte*8)]
    def guid(value):return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)
    def checked(result):
        if result<0:raise OSError(f'Windows shell-link HRESULT 0x{result & 0xffffffff:08x}')
    def method(pointer,index,*types):
        address=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[index]
        return ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,*types)(address)
    ole=ctypes.WinDLL('ole32');ole.CoInitialize.argtypes=[ctypes.c_void_p];ole.CoInitialize.restype=ctypes.c_long
    ole.CoCreateInstance.argtypes=[ctypes.POINTER(GUID),ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype=ctypes.c_long
    result=ole.CoInitialize(None);checked(result)
    link=ctypes.c_void_p();persist=ctypes.c_void_p()
    try:
        clsid=guid('00021401-0000-0000-c000-000000000046')
        interface=guid('000214f9-0000-0000-c000-000000000046')
        checked(ole.CoCreateInstance(ctypes.byref(clsid),None,1,ctypes.byref(interface),ctypes.byref(link)))
        persist_interface=guid('0000010b-0000-0000-c000-000000000046')
        checked(method(link,0,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p))(link,ctypes.byref(persist_interface),ctypes.byref(persist)))
        checked(method(persist,5,ctypes.c_wchar_p,ctypes.c_uint32)(persist,str(filename),0))
        buffer=ctypes.create_unicode_buffer(32768)
        checked(method(link,3,ctypes.c_wchar_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32)(link,buffer,len(buffer),None,0))
        return Path(buffer.value).resolve()
    finally:
        if persist.value:method(persist,2)(persist)
        if link.value:method(link,2)(link)
        ole.CoUninitialize()
