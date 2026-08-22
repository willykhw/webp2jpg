"""Windows 工作列圖示進度條（透過 ITaskbarList3）。

在 Windows 上讓工作列的程式圖示顯示進度（綠色進度條）。
非 Windows、缺少 comtypes、或任何 COM 失敗時一律安靜 no-op，不影響程式運作。

用法：
    tb = TaskbarProgress(root)
    tb.set(done, total)   # 綠色進度
    tb.error()            # 紅色（失敗）
    tb.clear()            # 移除進度條
"""

from __future__ import annotations

import sys

# ITaskbarList3 progress 狀態旗標
_TBPF_NOPROGRESS = 0x0
_TBPF_NORMAL = 0x2   # 綠色
_TBPF_ERROR = 0x4    # 紅色


class TaskbarProgress:
    def __init__(self, root):
        self._tb = None      # COM 物件；None 代表不支援
        self._hwnd = None
        if sys.platform != "win32":
            return
        try:
            self._init_win(root)
        except Exception:  # noqa: BLE001 - 任何失敗都退回不支援
            self._tb = None

    def _init_win(self, root):
        import ctypes
        from ctypes import c_int, c_ulonglong, c_void_p

        import comtypes.client
        from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

        class ITaskbarList3(IUnknown):
            _iid_ = GUID("{ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf}")
            _methods_ = [
                COMMETHOD([], HRESULT, "HrInit"),
                COMMETHOD([], HRESULT, "AddTab", (["in"], c_void_p, "hwnd")),
                COMMETHOD([], HRESULT, "DeleteTab", (["in"], c_void_p, "hwnd")),
                COMMETHOD([], HRESULT, "ActivateTab", (["in"], c_void_p, "hwnd")),
                COMMETHOD([], HRESULT, "SetActiveAlt", (["in"], c_void_p, "hwnd")),
                COMMETHOD([], HRESULT, "MarkFullscreenWindow",
                          (["in"], c_void_p, "hwnd"), (["in"], c_int, "fFullscreen")),
                # ITaskbarList3 起：SetProgressValue 在 SetProgressState 之前
                COMMETHOD([], HRESULT, "SetProgressValue",
                          (["in"], c_void_p, "hwnd"),
                          (["in"], c_ulonglong, "ullCompleted"),
                          (["in"], c_ulonglong, "ullTotal")),
                COMMETHOD([], HRESULT, "SetProgressState",
                          (["in"], c_void_p, "hwnd"), (["in"], c_int, "tbpFlags")),
            ]

        clsid_taskbarlist = GUID("{56FDF344-FD6D-11d0-958A-006097C9A090}")
        root.update_idletasks()
        # tkinter 的 winfo_id 是子視窗；工作列按鈕屬於最上層視窗，取其父 HWND
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        self._hwnd = hwnd or root.winfo_id()
        self._tb = comtypes.client.CreateObject(
            clsid_taskbarlist, interface=ITaskbarList3
        )
        self._tb.HrInit()

    def set(self, done, total):
        if not self._tb:
            return
        try:
            if total and total > 0:
                self._tb.SetProgressState(self._hwnd, _TBPF_NORMAL)
                self._tb.SetProgressValue(self._hwnd, int(max(0, done)), int(total))
            else:
                self._tb.SetProgressState(self._hwnd, _TBPF_NOPROGRESS)
        except Exception:  # noqa: BLE001
            self._tb = None

    def error(self):
        if not self._tb:
            return
        try:
            self._tb.SetProgressState(self._hwnd, _TBPF_ERROR)
        except Exception:  # noqa: BLE001
            self._tb = None

    def clear(self):
        if not self._tb:
            return
        try:
            self._tb.SetProgressState(self._hwnd, _TBPF_NOPROGRESS)
        except Exception:  # noqa: BLE001
            self._tb = None
