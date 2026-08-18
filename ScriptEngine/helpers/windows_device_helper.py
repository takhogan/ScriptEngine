import os

from ScriptEngine.common.logging.script_logger import ScriptLogger
script_logger = ScriptLogger()


class WindowsDeviceHelper:
    """Windows only window/process lookups backed by ctypes.

    The win32 imports live inside the methods so this module stays importable on
    other platforms.
    """

    @staticmethod
    def get_window_process_name(window_title):
        """Return the image name of the process owning the top level window titled
        window_title, or None if no such window exists.

        Cheaper than shelling out to tasklist, which spawns a process and walks every
        task on the machine for what is a single user32 lookup.
        """
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        # FindWindowW matches the full title case insensitively, same as tasklist's
        # "WINDOWTITLE eq" filter
        hwnd = user32.FindWindowW(None, window_title)
        if not hwnd:
            return None

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        process_handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not process_handle:
            script_logger.log(
                'WINDOWS DEVICE HELPER: unable to open process {} for window {}'.format(
                    pid.value, window_title
                ),
                level='debug'
            )
            return None
        try:
            path_length = wintypes.DWORD(260)
            path_buffer = ctypes.create_unicode_buffer(path_length.value)
            if not kernel32.QueryFullProcessImageNameW(
                process_handle, 0, path_buffer, ctypes.byref(path_length)
            ):
                return None
            return os.path.basename(path_buffer.value)
        finally:
            kernel32.CloseHandle(process_handle)

    @staticmethod
    def window_belongs_to_process(window_title, process_name):
        """True when a top level window titled window_title exists and is owned by a
        process whose image name contains process_name (case insensitive)."""
        owner = WindowsDeviceHelper.get_window_process_name(window_title)
        return owner is not None and process_name.lower() in owner.lower()
