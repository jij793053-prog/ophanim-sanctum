@echo off
setlocal
set "OPHANIM_BAT_SELF=%~f0"
set "OPHANIM_BAT_DIR=%~dp0"
set "OPHANIM_BAT_ARG=%~1"
start "" "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand JAByAGEAdwA9AFsAUwB5AHMAdABlAG0ALgBJAE8ALgBGAGkAbABlAF0AOgA6AFIAZQBhAGQAQQBsAGwAVABlAHgAdAAoACQAZQBuAHYAOgBPAFAASABBAE4ASQBNAF8AQgBBAFQAXwBTAEUATABGACwAWwBTAHkAcwB0AGUAbQAuAFQAZQB4AHQALgBFAG4AYwBvAGQAaQBuAGcAXQA6ADoAVQBUAEYAOAApADsAJABtAD0AJwAjACMAIwBPAFAASABBAE4ASQBNAF8AUABTAF8AQgBPAEQAWQAjACMAIwAnADsAJABpAD0AJAByAGEAdwAuAEkAbgBkAGUAeABPAGYAKAAkAG0AKQA7AGkAZgAoACQAaQAgAC0AZwBlACAAMAApAHsAJgAgACgAWwBzAGMAcgBpAHAAdABiAGwAbwBjAGsAXQA6ADoAQwByAGUAYQB0AGUAKAAkAHIAYQB3AC4AUwB1AGIAcwB0AHIAaQBuAGcAKAAkAGkAKwAkAG0ALgBMAGUAbgBnAHQAaAApACkAKQB9AA==
exit /b 0
###OPHANIM_PS_BODY###
$ErrorActionPreference = 'Stop'
$RootDir  = ($env:OPHANIM_BAT_DIR).TrimEnd('\', '/')
$BatSelf  = $env:OPHANIM_BAT_SELF
$Arg0     = [string]$env:OPHANIM_BAT_ARG
$HtmlFile = Join-Path $RootDir 'ophanim_toy_sanctum.html'
$CacheDir = Join-Path $RootDir '.ophanim_toy_cache'
$Port     = 18791
$HealthUrl = "http://127.0.0.1:$Port/api/health"
$AppUrl    = "http://127.0.0.1:$Port/ophanim_toy_sanctum.html?ws=ws://127.0.0.1:$Port/ws"

New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null

# 1. Register current-user URL protocol `ophanim-toy-wp://` (zero Admin required)
try {
    if ($BatSelf -and (Test-Path -LiteralPath $BatSelf)) {
        $protoKey = 'HKCU:\Software\Classes\ophanim-toy-wp'
        $cmdKey   = "$protoKey\shell\open\command"
        if (-not (Test-Path $cmdKey)) {
            New-Item -Path $cmdKey -Force | Out-Null
        }
        Set-ItemProperty -Path $protoKey -Name '(Default)' -Value 'URL:Ophanim Toy Wallpaper Helper' -Force
        Set-ItemProperty -Path $protoKey -Name 'URL Protocol' -Value '' -Force
        $cmdVal = '"' + $BatSelf + '" "%1"'
        Set-ItemProperty -Path $cmdKey -Name '(Default)' -Value $cmdVal -Force
    }
} catch {}

function Test-HostAlive {
    try {
        $req = [System.Net.HttpWebRequest]::Create($HealthUrl)
        $req.Proxy = $null
        $req.Timeout = 500
        $resp = $req.GetResponse()
        $ok = ([int]$resp.StatusCode -eq 200)
        $resp.Close()
        return $ok
    } catch {
        return $false
    }
}

function Find-ChromiumExe {
    $cands = @(
        Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
        Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'
        Join-Path $env:LocalAppData 'Microsoft\Edge\Application\msedge.exe'
        Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
        Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'
        Join-Path $env:LocalAppData 'Google\Chrome\Application\chrome.exe'
    )
    foreach ($c in $cands) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Open-ToyAppWindow {
    $browser = Find-ChromiumExe
    $target = if (Test-HostAlive) { $AppUrl } else { ([System.Uri]$HtmlFile).AbsoluteUri }
    if ($browser) {
        $appProf = Join-Path $CacheDir 'toy_app_window'
        New-Item -ItemType Directory -Path $appProf -Force | Out-Null
        Start-Process -FilePath $browser -ArgumentList @(
            "--user-data-dir=$appProf",
            "--app=$target",
            "--window-size=1560,940",
            "--force-dark-mode",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate,EdgeSidebar,msEdgeSidebarV2"
        ) | Out-Null
    } else {
        Start-Process $target | Out-Null
    }
}

$IsWakeOnly = ($Arg0 -like 'ophanim-toy-wp:*') -or ($Arg0 -eq '--headless-daemon')

if (Test-HostAlive) {
    if (-not $IsWakeOnly) {
        Open-ToyAppWindow
    }
    exit 0
}

$CsSource = @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

public static class OphanimToyNativeHost
{
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int x; public int y; }

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int left; public int top; public int right; public int bottom; }

    [StructLayout(LayoutKind.Sequential)]
    public struct MSG { public IntPtr hwnd; public uint message; public IntPtr wParam; public IntPtr lParam; public uint time; public POINT pt; }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct OSVERSIONINFOW
    {
        public uint dwOSVersionInfoSize;
        public uint dwMajorVersion;
        public uint dwMinorVersion;
        public uint dwBuildNumber;
        public uint dwPlatformId;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string szCSDVersion;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IO_COUNTERS
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RAWINPUTDEVICE
    {
        public ushort usUsagePage;
        public ushort usUsage;
        public uint dwFlags;
        public IntPtr hwndTarget;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RAWINPUTHEADER
    {
        public uint dwType;
        public uint dwSize;
        public IntPtr hDevice;
        public IntPtr wParam;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WNDCLASSEXW
    {
        public uint cbSize;
        public uint style;
        public IntPtr lpfnWndProc;
        public int cbClsExtra;
        public int cbWndExtra;
        public IntPtr hInstance;
        public IntPtr hIcon;
        public IntPtr hCursor;
        public IntPtr hbrBackground;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpszMenuName;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpszClassName;
        public IntPtr hIconSm;
    }

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    private delegate IntPtr WndProcDelegate(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [DllImport("ntdll.dll")] private static extern int RtlGetVersion(ref OSVERSIONINFOW lpVersionInformation);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateJobObjectW(IntPtr lpJobAttributes, string lpName);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(IntPtr hJob, int infoType, IntPtr lpJobObjectInfo, uint cbJobObjectInfoLength);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool TerminateJobObject(IntPtr hJob, uint uExitCode);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, uint dwProcessId);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandleW(string lpModuleName);
    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    [DllImport("shell32.dll")]
    private static extern int SHQueryUserNotificationState(out int pquns);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindowW(string cls, string title);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindowExW(IntPtr parent, IntPtr after, string cls, string title);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc fn, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc fn, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassNameW(IntPtr hWnd, StringBuilder sb, int max);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder sb, int max);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsHungAppWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr hWnd, uint uCmd);
    [DllImport("user32.dll", SetLastError = true)] public static extern IntPtr SetParent(IntPtr child, IntPtr newParent);
    [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool EnableWindow(IntPtr hWnd, bool enable);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int cmd);
    [DllImport("user32.dll")] public static extern bool ScreenToClient(IntPtr hWnd, ref POINT lpPoint);
    [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool PostThreadMessageW(uint idThread, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern IntPtr SendMessageTimeoutW(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam, uint flags, uint timeout, out IntPtr result);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongW")] private static extern int GetWindowLong32(IntPtr hWnd, int idx);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongW")] private static extern int SetWindowLong32(IntPtr hWnd, int idx, int val);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] private static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int idx);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] private static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int idx, IntPtr val);

    private static long GetWinLongSafe(IntPtr hWnd, int idx)
    {
        return IntPtr.Size == 8 ? GetWindowLongPtr64(hWnd, idx).ToInt64() : (long)GetWindowLong32(hWnd, idx);
    }

    private static void SetWinLongSafe(IntPtr hWnd, int idx, long val)
    {
        int v32 = unchecked((int)(val & 0xFFFFFFFFL));
        if (IntPtr.Size == 8) SetWindowLongPtr64(hWnd, idx, new IntPtr(v32));
        else SetWindowLong32(hWnd, idx, v32);
    }

    [DllImport("user32.dll")] public static extern bool SetLayeredWindowAttributes(IntPtr hWnd, uint crKey, byte bAlpha, uint dwFlags);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool RedrawWindow(IntPtr hWnd, IntPtr rc, IntPtr rgn, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern bool SystemParametersInfoW(uint action, uint param, StringBuilder pvParam, uint winIni);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT pt);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rc);
    [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT pt);
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr hWnd, uint flags);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vKey);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int nIndex);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] private static extern bool SetProcessDpiAwarenessContext(IntPtr dpiContext);
    [DllImport("user32.dll")] private static extern uint GetDpiForSystem();
    [DllImport("user32.dll")] public static extern int GetMessageW(out MSG lpMsg, IntPtr hWnd, uint min, uint max);
    [DllImport("user32.dll")] private static extern bool TranslateMessage(ref MSG lpMsg);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr DispatchMessageW(ref MSG lpMsg);
    [DllImport("user32.dll")] private static extern void PostQuitMessage(int nExitCode);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint procId);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern ushort RegisterClassExW(ref WNDCLASSEXW lpwcx);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool UnregisterClassW(string lpClassName, IntPtr hInstance);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateWindowExW(
        uint dwExStyle, string lpClassName, string lpWindowName, uint dwStyle,
        int x, int y, int nWidth, int nHeight,
        IntPtr hWndParent, IntPtr hMenu, IntPtr hInstance, IntPtr lpParam);
    [DllImport("user32.dll")] private static extern bool DestroyWindow(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr DefWindowProcW(IntPtr hWnd, uint uMsg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterRawInputDevices(
        [MarshalAs(UnmanagedType.LPArray, SizeParamIndex = 1)] RAWINPUTDEVICE[] pRawInputDevices,
        uint uiNumDevices,
        uint cbSize);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint GetRawInputData(
        IntPtr hRawInput,
        uint uiCommand,
        IntPtr pData,
        ref uint pcbSize,
        uint cbSizeHeader);

    [ComImport, Guid("56FDF344-FD6D-11D0-958A-006097C9A090")]
    private class CTaskbarList { }

    [ComImport, Guid("56FDF342-FD6D-11D0-958A-006097C9A090"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface ITaskbarList
    {
        [PreserveSig] int HrInit();
        [PreserveSig] int AddTab(IntPtr hwnd);
        [PreserveSig] int DeleteTab(IntPtr hwnd);
        [PreserveSig] int ActivateTab(IntPtr hwnd);
        [PreserveSig] int SetActiveAlt(IntPtr hwnd);
    }

    private sealed class WsClientEntry
    {
        public readonly Stream Stream;
        public readonly object WriteLock = new object();
        public volatile bool IsWallpaper;
        public WsClientEntry(Stream stream, bool isWallpaper)
        {
            Stream = stream;
            IsWallpaper = isWallpaper;
        }
    }

    private const int GWL_STYLE = -16;
    private const int GWL_EXSTYLE = -20;
    private const long WS_CHILD = 0x40000000L;
    private const long WS_VISIBLE = 0x10000000L;
    private const long WS_DISABLED = 0x08000000L;
    private const long WS_CLIPSIBLINGS = 0x04000000L;
    private const long WS_CLIPCHILDREN = 0x02000000L;
    private const long WS_POPUP = 0x80000000L;
    private const long WS_CAPTION = 0x00C00000L;
    private const long WS_BORDER = 0x00800000L;
    private const long WS_DLGFRAME = 0x00400000L;
    private const long WS_THICKFRAME = 0x00040000L;
    private const long WS_MINIMIZEBOX = 0x00020000L;
    private const long WS_MAXIMIZEBOX = 0x00010000L;
    private const long WS_SYSMENU = 0x00080000L;

    private const long WS_EX_NOPARENTNOTIFY = 0x00000004L;
    private const long WS_EX_TRANSPARENT = 0x00000020L;
    private const long WS_EX_TOOLWINDOW = 0x00000080L;
    private const long WS_EX_WINDOWEDGE = 0x00000100L;
    private const long WS_EX_CLIENTEDGE = 0x00000200L;
    private const long WS_EX_APPWINDOW = 0x00040000L;
    private const long WS_EX_LAYERED = 0x00080000L;
    private const long WS_EX_NOACTIVATE = 0x08000000L;

    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOZORDER = 0x0004;
    private const uint SWP_NOACTIVATE = 0x0010;
    private const uint SWP_FRAMECHANGED = 0x0020;
    private const uint SWP_SHOWWINDOW = 0x0040;
    private const uint SWP_ASYNCWINDOWPOS = 0x4000;

    private const uint SMTO_ABORTIFHUNG = 0x0002;
    private const uint GW_HWNDNEXT = 2;
    private const int SW_HIDE = 0;
    private const int SW_SHOW = 5;
    private const uint RDW_ASYNC_REFRESH = 0x0085; // RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN (NO RDW_UPDATENOW)

    private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
    private const int JobObjectExtendedLimitInformation = 9;
    private const uint PROCESS_SET_QUOTA = 0x0100;
    private const uint PROCESS_TERMINATE = 0x0001;

    private const uint WM_DESTROY = 0x0002;
    private const uint WM_CLOSE = 0x0010;
    private const uint WM_QUIT = 0x0012;
    private const uint WM_INPUT = 0x00FF;
    private const uint RID_INPUT = 0x10000003;
    private const uint RIM_TYPEMOUSE = 0;
    private const uint RIDEV_REMOVE = 0x00000001;
    private const uint RIDEV_INPUTSINK = 0x00000100;
    private const ushort RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001;
    private const ushort RI_MOUSE_LEFT_BUTTON_UP = 0x0002;
    private const ushort RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004;
    private const ushort RI_MOUSE_RIGHT_BUTTON_UP = 0x0008;
    private const ushort RI_MOUSE_WHEEL = 0x0400;

    private static string _htmlPath;
    private static string _cacheDir;
    private static string _configPath;
    private static string _browserExe;
    private static int _port = 18791;

    private static readonly object _wsLock = new object();
    private static readonly List<WsClientEntry> _wsClients = new List<WsClientEntry>();
    private static readonly object _wpLock = new object();

    private static volatile bool _wpActive = false;
    private static volatile bool _wallpaperApiTouched = false;
    private static volatile bool _lastOccludedState = false;
    private static volatile bool _shuttingDown = false;
    private static string _wpMode = "agy_live";
    private static string _beamMode = "ambient";
    private static string _origWallpaper = "";
    private static IntPtr _wpHwnd = IntPtr.Zero;
    private static IntPtr _wpParentHwnd = IntPtr.Zero;
    private static IntPtr _wpProgmanHwnd = IntPtr.Zero;
    private static IntPtr _taskbarHiddenHwnd = IntPtr.Zero;
    private static IntPtr _wpJobHandle = IntPtr.Zero;
    private static int _wpPid = 0;
    private static bool _wpIs24H2Mode = false;
    private static readonly List<int> _spawnedWpPids = new List<int>();

    // Lock-free Raw Input state (registered ONLY while _wpActive is true!)
    private static readonly object _rawInputLock = new object();
    private static Thread _rawInputThread = null;
    private static IntPtr _rawMsgHwnd = IntPtr.Zero;
    private static uint _rawThreadId = 0;
    private static IntPtr _rawInputBuf = IntPtr.Zero;
    private const int _rawInputBufSize = 256;
    private static WndProcDelegate _rawWndProcRef = null;
    private static volatile bool _mouseButtonsSwapped = false;
    private static int _wheelDeltaRaw = 0;
    private static int _clickPending = 0;
    private static int _ldownX = 0;
    private static int _ldownY = 0;
    private static long _ldownTicks = 0;
    private static int _hasLdown = 0;

    private static void EnableDpiAwarenessSafe()
    {
        try {
            if (SetProcessDpiAwarenessContext(new IntPtr(-4))) return;
        } catch { }
        try { SetProcessDPIAware(); } catch { }
    }

    private static bool IsWin11_24H2OrLater()
    {
        if (Environment.OSVersion.Version.Build >= 26000) return true;
        try {
            OSVERSIONINFOW osv = new OSVERSIONINFOW();
            osv.dwOSVersionInfoSize = (uint)Marshal.SizeOf(typeof(OSVERSIONINFOW));
            if (RtlGetVersion(ref osv) == 0 && osv.dwBuildNumber >= 26000) return true;
        } catch { }
        return false;
    }

    private static bool IsWindowResponsive(IntPtr hwnd, uint timeoutMs)
    {
        if (hwnd == IntPtr.Zero || !IsWindow(hwnd)) return false;
        try {
            if (IsHungAppWindow(hwnd)) return false;
        } catch { }
        IntPtr dummy;
        IntPtr res = SendMessageTimeoutW(hwnd, 0, IntPtr.Zero, IntPtr.Zero, SMTO_ABORTIFHUNG, timeoutMs, out dummy);
        return res != IntPtr.Zero;
    }

    private static void GetPrimaryScreenMetrics(out int physW, out int physH, out int dipW, out int dipH)
    {
        EnableDpiAwarenessSafe();
        physW = Math.Max(800, GetSystemMetrics(0));
        physH = Math.Max(600, GetSystemMetrics(1));
        double scale = 1.0;
        try {
            uint dpi = GetDpiForSystem();
            if (dpi >= 96) scale = (double)dpi / 96.0;
        } catch { }
        if (scale <= 0.1) scale = 1.0;
        dipW = Math.Max(800, (int)Math.Round(physW / scale));
        dipH = Math.Max(600, (int)Math.Round(physH / scale));
    }

    private static void PresetWallpaperProfilePrefs(string wpProfile, int dipW, int dipH)
    {
        try {
            string defDir = Path.Combine(wpProfile, "Default");
            Directory.CreateDirectory(defDir);
            string prefsPath = Path.Combine(defDir, "Preferences");
            JavaScriptSerializer jss = new JavaScriptSerializer();
            jss.MaxJsonLength = 4 * 1024 * 1024;
            Dictionary<string, object> prefs = new Dictionary<string, object>();
            if (File.Exists(prefsPath)) {
                try {
                    Dictionary<string, object> loaded = jss.Deserialize<Dictionary<string, object>>(File.ReadAllText(prefsPath, Encoding.UTF8));
                    if (loaded != null) prefs = loaded;
                } catch { }
            }
            Dictionary<string, object> browserSec = new Dictionary<string, object>();
            if (prefs.ContainsKey("browser") && prefs["browser"] is Dictionary<string, object>) {
                browserSec = (Dictionary<string, object>)prefs["browser"];
            }
            Dictionary<string, object> placement = new Dictionary<string, object>();
            placement["left"] = 0;
            placement["top"] = 0;
            placement["right"] = dipW;
            placement["bottom"] = dipH;
            placement["maximized"] = false;
            placement["minimized"] = false;
            placement["work_area_left"] = 0;
            placement["work_area_top"] = 0;
            placement["work_area_right"] = dipW;
            placement["work_area_bottom"] = dipH;
            browserSec["window_placement"] = placement;
            browserSec["has_seen_welcome_page"] = true;
            prefs["browser"] = browserSec;

            Dictionary<string, object> profSec = new Dictionary<string, object>();
            if (prefs.ContainsKey("profile") && prefs["profile"] is Dictionary<string, object>) {
                profSec = (Dictionary<string, object>)prefs["profile"];
            }
            profSec["exit_type"] = "Normal";
            profSec["exited_cleanly"] = true;
            prefs["profile"] = profSec;

            File.WriteAllText(prefsPath, jss.Serialize(prefs), Encoding.UTF8);
        } catch { }
    }

    private static IntPtr CreateKillOnCloseJobObject()
    {
        IntPtr hJob = CreateJobObjectW(IntPtr.Zero, null);
        if (hJob == IntPtr.Zero) return IntPtr.Zero;
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        int sz = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
        IntPtr ptr = Marshal.AllocHGlobal(sz);
        try {
            Marshal.StructureToPtr(info, ptr, false);
            if (!SetInformationJobObject(hJob, JobObjectExtendedLimitInformation, ptr, (uint)sz)) {
                CloseHandle(hJob);
                return IntPtr.Zero;
            }
        } finally {
            Marshal.FreeHGlobal(ptr);
        }
        return hJob;
    }

    private static void AssignPidToJobSafe(IntPtr hJob, uint pid)
    {
        if (hJob == IntPtr.Zero || pid == 0) return;
        IntPtr hProc = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, false, pid);
        if (hProc != IntPtr.Zero) {
            try { AssignProcessToJobObject(hJob, hProc); } catch { }
            finally { CloseHandle(hProc); }
        }
    }

    private static void TerminateAndCloseJobObject()
    {
        if (_wpJobHandle != IntPtr.Zero) {
            IntPtr h = _wpJobHandle;
            _wpJobHandle = IntPtr.Zero;
            try { TerminateJobObject(h, 0); } catch { }
            try { CloseHandle(h); } catch { }
        }
    }

    private static void HideFromTaskbarOnce(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero || _taskbarHiddenHwnd == hwnd) return;
        IntPtr tray = FindWindowW("Shell_TrayWnd", null);
        if (tray != IntPtr.Zero) {
            try {
                if (IsHungAppWindow(tray)) return;
            } catch { }
        }
        _taskbarHiddenHwnd = hwnd;
        Thread t = new Thread(delegate() {
            try {
                ITaskbarList tbl = (ITaskbarList)(new CTaskbarList());
                try {
                    if (tbl.HrInit() == 0) tbl.DeleteTab(hwnd);
                } finally {
                    Marshal.ReleaseComObject(tbl);
                }
            } catch { }
        });
        t.IsBackground = true;
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join(400);
    }

    private static string GetWinClass(IntPtr h)
    {
        if (h == IntPtr.Zero) return "";
        StringBuilder sb = new StringBuilder(128);
        int n = GetClassNameW(h, sb, 128);
        return n > 0 ? sb.ToString() : "";
    }

    private static string GetWinTitle(IntPtr h)
    {
        if (h == IntPtr.Zero) return "";
        StringBuilder sb = new StringBuilder(512);
        int n = GetWindowTextW(h, sb, 512);
        return n > 0 ? sb.ToString() : "";
    }

    private static bool IsWallpaperWindowSignature(IntPtr h)
    {
        if (h == IntPtr.Zero || !IsWindow(h)) return false;
        if (GetWinClass(h) != "Chrome_WidgetWin_1") return false;
        string t = GetWinTitle(h);
        return t != null && t.ToUpperInvariant().Contains("OPHANIM WALLPAPER");
    }

    private static bool IsValidTrackedWallpaperHwnd(IntPtr h)
    {
        if (!IsWallpaperWindowSignature(h)) return false;
        uint pid = 0;
        GetWindowThreadProcessId(h, out pid);
        if (pid == 0) return false;
        if (_wpPid > 0 && pid != (uint)_wpPid && !_spawnedWpPids.Contains((int)pid)) {
            return false;
        }
        return true;
    }

    private static List<IntPtr> FindWallpaperHwnds()
    {
        List<IntPtr> list = new List<IntPtr>();
        List<IntPtr> workerParents = new List<IntPtr>();
        EnumWindowsProc checkCb = delegate(IntPtr h, IntPtr lp) {
            string cls = GetWinClass(h);
            if (cls == "Chrome_WidgetWin_1") {
                string t = GetWinTitle(h);
                if (t != null && t.ToUpperInvariant().Contains("OPHANIM WALLPAPER")) {
                    if (!list.Contains(h)) list.Add(h);
                }
            } else if (cls == "WorkerW") {
                if (!workerParents.Contains(h)) workerParents.Add(h);
            }
            return true;
        };
        EnumWindows(checkCb, IntPtr.Zero);
        IntPtr progman = FindWindowW("Progman", null);
        if (progman != IntPtr.Zero) EnumChildWindows(progman, checkCb, IntPtr.Zero);
        foreach (IntPtr ww in workerParents) {
            EnumChildWindows(ww, checkCb, IntPtr.Zero);
        }
        return list;
    }

    private static IntPtr FindClassicWallpaperWorkerW()
    {
        IntPtr wallpaperWorkerW = IntPtr.Zero;
        EnumWindows(delegate(IntPtr topH, IntPtr lp) {
            IntPtr dv = FindWindowExW(topH, IntPtr.Zero, "SHELLDLL_DefView", null);
            if (dv != IntPtr.Zero) {
                IntPtr w = FindWindowExW(IntPtr.Zero, topH, "WorkerW", null);
                if (w != IntPtr.Zero) {
                    wallpaperWorkerW = w;
                    return false;
                }
            }
            return true;
        }, IntPtr.Zero);
        return wallpaperWorkerW;
    }

    private static string ReadSystemWallpaper()
    {
        try {
            StringBuilder sb = new StringBuilder(1024);
            if (SystemParametersInfoW(0x0073, 1024, sb, 0)) {
                string p = sb.ToString().Trim();
                if (p.Length > 0 && File.Exists(p)) return p;
            }
        } catch { }
        return "";
    }

    private static bool ApplyWallpaperAttach(IntPtr hwnd, int physW, int physH, bool allowSpawnWorkerW)
    {
        EnableDpiAwarenessSafe();
        if (!IsValidTrackedWallpaperHwnd(hwnd)) return false;

        IntPtr progman = FindWindowW("Progman", null);
        if (!IsWindowResponsive(progman, 250)) return false;

        bool is24H2 = IsWin11_24H2OrLater();
        IntPtr defviewInProgman = FindWindowExW(progman, IntPtr.Zero, "SHELLDLL_DefView", null);
        IntPtr existingWorkerW = (defviewInProgman != IntPtr.Zero)
            ? FindWindowExW(progman, IntPtr.Zero, "WorkerW", null)
            : FindClassicWallpaperWorkerW();

        // Send 0x052C (0xD, 0x1 ONLY, SMTO_ABORTIFHUNG, 500ms) ONLY on initial attach when WorkerW doesn't exist
        if (allowSpawnWorkerW && existingWorkerW == IntPtr.Zero) {
            IntPtr dummy;
            IntPtr msgRes = SendMessageTimeoutW(progman, 0x052C, new IntPtr(0xD), new IntPtr(1), SMTO_ABORTIFHUNG, 500, out dummy);
            if (msgRes == IntPtr.Zero || !IsWindowResponsive(progman, 250)) return false;
            defviewInProgman = FindWindowExW(progman, IntPtr.Zero, "SHELLDLL_DefView", null);
        }

        long stripStyle = WS_POPUP | WS_CAPTION | WS_BORDER | WS_DLGFRAME | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU;
        long childFlags = WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN | WS_DISABLED;
        long exStrip = WS_EX_APPWINDOW | WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE;
        long exAdd = WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_NOPARENTNOTIFY | WS_EX_LAYERED;

        if (defviewInProgman != IntPtr.Zero || is24H2) {
            // Windows 11 24H2+ RaisedDesktop: NEVER fall back to classic SWP_NOZORDER covering desktop icons
            if (defviewInProgman == IntPtr.Zero) return false;

            IntPtr curParent = GetParent(hwnd);
            long curStyle = GetWinLongSafe(hwnd, GWL_STYLE) & 0xFFFFFFFFL;
            long newStyle = ((curStyle & ~stripStyle) | childFlags) & 0xFFFFFFFFL;
            long curEx = GetWinLongSafe(hwnd, GWL_EXSTYLE) & 0xFFFFFFFFL;
            long newEx = ((curEx & ~exStrip) | exAdd) & 0xFFFFFFFFL;

            SetWinLongSafe(hwnd, GWL_STYLE, newStyle);
            SetWinLongSafe(hwnd, GWL_EXSTYLE, newEx);
            SetLayeredWindowAttributes(hwnd, 0, 255, 0x02);
            EnableWindow(hwnd, false);

            if (curParent != progman) {
                IntPtr prevParent = SetParent(hwnd, progman);
                if (prevParent == IntPtr.Zero || GetParent(hwnd) != progman) {
                    return false;
                }
                SetWinLongSafe(hwnd, GWL_STYLE, newStyle);
                SetWinLongSafe(hwnd, GWL_EXSTYLE, newEx);
                SetLayeredWindowAttributes(hwnd, 0, 255, 0x02);
                EnableWindow(hwnd, false);
                HideFromTaskbarOnce(hwnd);
            }

            POINT pt = new POINT { x = 0, y = 0 };
            ScreenToClient(progman, ref pt);
            SetWindowPos(hwnd, defviewInProgman, pt.x, pt.y, physW, physH, SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW);

            IntPtr workerwInProgman = FindWindowExW(progman, IntPtr.Zero, "WorkerW", null);
            if (workerwInProgman != IntPtr.Zero && workerwInProgman != hwnd) {
                if (GetWindow(hwnd, GW_HWNDNEXT) != workerwInProgman) {
                    SetWindowPos(workerwInProgman, hwnd, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS);
                }
            }

            _wpParentHwnd = progman;
            _wpProgmanHwnd = progman;
            _wpIs24H2Mode = true;
            return true;
        }

        // Classic Windows 10 / Windows 11 <=23H2 WorkerW architecture (require actual WorkerW; never cover icons on Progman)
        IntPtr wallpaperWorkerW = FindClassicWallpaperWorkerW();
        if (wallpaperWorkerW == IntPtr.Zero || !IsWindowResponsive(wallpaperWorkerW, 250)) {
            return false;
        }

        IntPtr curP = GetParent(hwnd);
        long cStyle = GetWinLongSafe(hwnd, GWL_STYLE) & 0xFFFFFFFFL;
        long nStyle = ((cStyle & ~stripStyle) | childFlags) & 0xFFFFFFFFL;
        long cEx = GetWinLongSafe(hwnd, GWL_EXSTYLE) & 0xFFFFFFFFL;
        long nEx = ((cEx & ~exStrip) | exAdd) & 0xFFFFFFFFL;

        SetWinLongSafe(hwnd, GWL_STYLE, nStyle);
        SetWinLongSafe(hwnd, GWL_EXSTYLE, nEx);
        SetLayeredWindowAttributes(hwnd, 0, 255, 0x02);
        EnableWindow(hwnd, false);

        if (curP != wallpaperWorkerW) {
            IntPtr prevP = SetParent(hwnd, wallpaperWorkerW);
            if (prevP == IntPtr.Zero || GetParent(hwnd) != wallpaperWorkerW) {
                return false;
            }
            SetWinLongSafe(hwnd, GWL_STYLE, nStyle);
            SetWinLongSafe(hwnd, GWL_EXSTYLE, nEx);
            SetLayeredWindowAttributes(hwnd, 0, 255, 0x02);
            EnableWindow(hwnd, false);
            HideFromTaskbarOnce(hwnd);
        }

        POINT ptClassic = new POINT { x = 0, y = 0 };
        ScreenToClient(wallpaperWorkerW, ref ptClassic);
        SetWindowPos(hwnd, IntPtr.Zero, ptClassic.x, ptClassic.y, physW, physH, SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW);

        _wpParentHwnd = wallpaperWorkerW;
        _wpProgmanHwnd = progman;
        _wpIs24H2Mode = false;
        return true;
    }

    // Read-only diff periodic health check (10-15s cadence, under Monitor.TryEnter(_wpLock), ZERO 0x052C / COM spam!)
    private static void PeriodicWallpaperHealthCheck()
    {
        if (!_wpActive) return;
        bool acquired = false;
        try {
            Monitor.TryEnter(_wpLock, 0, ref acquired);
            if (!acquired) return;
            if (!_wpActive) return;

            if (!IsValidTrackedWallpaperHwnd(_wpHwnd)) {
                _wpActive = false;
                _wpHwnd = IntPtr.Zero;
                StopRawInput();
                return;
            }

            IntPtr progman = FindWindowW("Progman", null);
            if (!IsWindowResponsive(progman, 250)) {
                return;
            }

            int physW, physH, dipW, dipH;
            GetPrimaryScreenMetrics(out physW, out physH, out dipW, out dipH);

            // If Explorer restarted and Progman HWND changed, re-attach once cleanly
            if (_wpProgmanHwnd != IntPtr.Zero && progman != _wpProgmanHwnd) {
                ApplyWallpaperAttach(_wpHwnd, physW, physH, true);
                return;
            }

            IntPtr curParent = GetParent(_wpHwnd);
            RECT rc;
            bool rectOk = GetWindowRect(_wpHwnd, out rc) &&
                          Math.Abs(rc.left) <= 2 && Math.Abs(rc.top) <= 2 &&
                          Math.Abs((rc.right - rc.left) - physW) <= 2 &&
                          Math.Abs((rc.bottom - rc.top) - physH) <= 2;

            if (_wpIs24H2Mode) {
                IntPtr defview = FindWindowExW(progman, IntPtr.Zero, "SHELLDLL_DefView", null);
                if (defview == IntPtr.Zero) return;

                bool parentOk = (curParent == progman);
                bool zOrderOk = (GetWindow(defview, GW_HWNDNEXT) == _wpHwnd);
                IntPtr workerwInProgman = FindWindowExW(progman, IntPtr.Zero, "WorkerW", null);
                bool workerBehindOk = (workerwInProgman == IntPtr.Zero || workerwInProgman == _wpHwnd || GetWindow(_wpHwnd, GW_HWNDNEXT) == workerwInProgman);

                if (parentOk && rectOk && zOrderOk && workerBehindOk) {
                    return; // Already properly pinned -> complete NO-OP!
                }

                if (!parentOk) {
                    ApplyWallpaperAttach(_wpHwnd, physW, physH, false);
                    return;
                }
                if (!rectOk || !zOrderOk) {
                    POINT pt = new POINT { x = 0, y = 0 };
                    ScreenToClient(progman, ref pt);
                    SetWindowPos(_wpHwnd, defview, pt.x, pt.y, physW, physH, SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_ASYNCWINDOWPOS);
                }
                if (!workerBehindOk && workerwInProgman != IntPtr.Zero && workerwInProgman != _wpHwnd) {
                    SetWindowPos(workerwInProgman, _wpHwnd, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS);
                }
            } else {
                bool parentOk = (_wpParentHwnd != IntPtr.Zero && IsWindow(_wpParentHwnd) && curParent == _wpParentHwnd);
                if (parentOk && rectOk) {
                    return; // Already properly pinned -> complete NO-OP!
                }
                if (!parentOk) {
                    ApplyWallpaperAttach(_wpHwnd, physW, physH, false);
                } else {
                    POINT ptClassic = new POINT { x = 0, y = 0 };
                    ScreenToClient(_wpParentHwnd, ref ptClassic);
                    SetWindowPos(_wpHwnd, IntPtr.Zero, ptClassic.x, ptClassic.y, physW, physH, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_ASYNCWINDOWPOS);
                }
            }
        } catch {
        } finally {
            if (acquired) Monitor.Exit(_wpLock);
        }
    }

    private static void DetachAndCloseExisting(bool restoreStatic)
    {
        StopRawInput();

        List<IntPtr> hwnds = new List<IntPtr>();
        if (IsValidTrackedWallpaperHwnd(_wpHwnd)) {
            hwnds.Add(_wpHwnd);
        }
        foreach (IntPtr foundH in FindWallpaperHwnds()) {
            if (IsWallpaperWindowSignature(foundH) && !hwnds.Contains(foundH)) {
                hwnds.Add(foundH);
            }
        }

        // Hide asynchronously & close WITHOUT synchronous SetParent(h, 0) (kernel detaches child HWND cleanly on exit!)
        foreach (IntPtr h in hwnds) {
            try {
                uint pid = 0;
                GetWindowThreadProcessId(h, out pid);
                ShowWindowAsync(h, SW_HIDE);
                PostMessageW(h, WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
                if (pid > 0 && !_spawnedWpPids.Contains((int)pid)) _spawnedWpPids.Add((int)pid);
            } catch { }
        }

        // Atomically terminate the browser process tree via Job Object
        TerminateAndCloseJobObject();

        // Fallback kill for any tracked PIDs (properly wrapped in using)
        foreach (int pid in _spawnedWpPids.ToArray()) {
            try {
                using (Process p = Process.GetProcessById(pid)) {
                    if (!p.HasExited) p.Kill();
                }
            } catch { }
        }
        _spawnedWpPids.Clear();
        _wpHwnd = IntPtr.Zero;
        _wpParentHwnd = IntPtr.Zero;
        _wpProgmanHwnd = IntPtr.Zero;
        _taskbarHiddenHwnd = IntPtr.Zero;
        _wpPid = 0;
        _lastOccludedState = false;

        // Explorer-safe asynchronous desktop refresh (NEVER synchronous SPI_SETDESKWALLPAPER or RDW_UPDATENOW!)
        if (restoreStatic) {
            IntPtr progman = FindWindowW("Progman", null);
            if (progman != IntPtr.Zero) {
                bool hung = false;
                try { hung = IsHungAppWindow(progman); } catch { }
                if (!hung) {
                    RedrawWindow(progman, IntPtr.Zero, IntPtr.Zero, RDW_ASYNC_REFRESH);
                    IntPtr ww = FindWindowExW(progman, IntPtr.Zero, "WorkerW", null);
                    if (ww != IntPtr.Zero) {
                        bool wwHung = false;
                        try { wwHung = IsHungAppWindow(ww); } catch { }
                        if (!wwHung) {
                            ShowWindowAsync(ww, SW_SHOW);
                            RedrawWindow(ww, IntPtr.Zero, IntPtr.Zero, RDW_ASYNC_REFRESH);
                        }
                    }
                }
            }
        }
    }

    private static string EnableWallpaperInternal(string wpMode, string beamMode)
    {
        lock (_wpLock) {
            if (string.IsNullOrEmpty(_browserExe) || !File.Exists(_browserExe)) {
                return "{\"ok\":false,\"active\":false,\"error\":\"\u672a\u627e\u5230 Microsoft Edge \u6216 Chrome \u6d4f\u89c8\u5668\"}";
            }
            IntPtr progmanCheck = FindWindowW("Progman", null);
            if (!IsWindowResponsive(progmanCheck, 250)) {
                return "{\"ok\":false,\"active\":false,\"error\":\"Windows \u684c\u9762 Progman \u672a\u5c31\u7eea\u6216\u65e0\u54cd\u5e94\uff0c\u5df2\u5b89\u5168\u4e2d\u6b62\u5d4c\u5165\"}";
            }
            if (IsWin11_24H2OrLater() && FindWindowExW(progmanCheck, IntPtr.Zero, "SHELLDLL_DefView", null) == IntPtr.Zero) {
                return "{\"ok\":false,\"active\":false,\"error\":\"\u672a\u68c0\u6d4b\u5230 Win11 24H2 SHELLDLL_DefView \u56fe\u5c42\uff0c\u5df2\u963b\u6b62\u8986\u76d6\u684c\u9762\u56fe\u6807\"}";
            }
            if (string.IsNullOrEmpty(_origWallpaper)) {
                _origWallpaper = ReadSystemWallpaper();
            }
            DetachAndCloseExisting(false);

            int physW, physH, dipW, dipH;
            GetPrimaryScreenMetrics(out physW, out physH, out dipW, out dipH);

            string wpProfile = Path.Combine(_cacheDir, "toy_wp_profile");
            string wpDiskCache = Path.Combine(_cacheDir, "toy_wp_cache");
            Directory.CreateDirectory(wpProfile);
            Directory.CreateDirectory(wpDiskCache);
            PresetWallpaperProfilePrefs(wpProfile, dipW, dipH);

            string cleanMode = (wpMode == "ambient_eco") ? "ambient_eco" : "agy_live";
            string effBeam = (cleanMode == "ambient_eco") ? "ambient" : (string.IsNullOrEmpty(beamMode) ? "ambient" : beamMode);
            string ecoFlag = (cleanMode == "ambient_eco") ? "1" : "0";
            string wsForWp = string.Format("ws://127.0.0.1:{0}/ws?wallpaper=1", _port);
            string wpUrl = string.Format(
                "http://127.0.0.1:{0}/ophanim_toy_sanctum.html?ws={1}&wallpaper=1&wpMode={2}&beamMode={3}&eco={4}&t={5}",
                _port, Uri.EscapeDataString(wsForWp), Uri.EscapeDataString(cleanMode), Uri.EscapeDataString(effBeam), ecoFlag, DateTime.UtcNow.Ticks
            );

            // Assign spawned browser to a Win32 Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            _wpJobHandle = CreateKillOnCloseJobObject();

            bool isEdge = _browserExe.ToLowerInvariant().Contains("msedge");
            string kioskExtra = isEdge ? "--edge-kiosk-type=fullscreen " : "";
            string args = string.Format(
                "--user-data-dir=\"{0}\" --disk-cache-dir=\"{1}\" --window-position=0,0 --window-size={2},{3} --kiosk \"{4}\" {5}--no-first-run --no-default-browser-check --disable-extensions --disable-sync --disable-infobars --disable-session-crashed-bubble --autoplay-policy=no-user-gesture-required --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-features=CalculateNativeWinOcclusion,Translate,msEdgeSidebarV2",
                wpProfile, wpDiskCache, dipW, dipH, wpUrl, kioskExtra
            );

            ProcessStartInfo psi = new ProcessStartInfo(_browserExe, args);
            psi.UseShellExecute = false;
            using (Process proc = Process.Start(psi)) {
                if (proc != null) {
                    _wpPid = proc.Id;
                    _spawnedWpPids.Add(proc.Id);
                    if (_wpJobHandle != IntPtr.Zero) {
                        try { AssignProcessToJobObject(_wpJobHandle, proc.Handle); } catch { }
                    }
                }
            }

            IntPtr targetHwnd = IntPtr.Zero;
            Stopwatch sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < 15000) {
                List<IntPtr> found = FindWallpaperHwnds();
                if (found.Count > 0) {
                    targetHwnd = found[0];
                    break;
                }
                Thread.Sleep(45);
            }

            if (targetHwnd == IntPtr.Zero) {
                DetachAndCloseExisting(true);
                return "{\"ok\":false,\"active\":false,\"error\":\"\u7b49\u5f85\u58c1\u7eb8\u6e32\u67d3\u7a97\u53e3\u8d85\u65f6\uff0c\u5df2\u81ea\u52a8\u6e05\u7406\"}";
            }

            uint hwndPid = 0;
            GetWindowThreadProcessId(targetHwnd, out hwndPid);
            if (hwndPid > 0) {
                _wpPid = (int)hwndPid;
                if (!_spawnedWpPids.Contains((int)hwndPid)) _spawnedWpPids.Add((int)hwndPid);
                AssignPidToJobSafe(_wpJobHandle, hwndPid);
            }

            if (!ApplyWallpaperAttach(targetHwnd, physW, physH, true)) {
                DetachAndCloseExisting(true);
                return "{\"ok\":false,\"active\":false,\"error\":\"\u5d4c\u5165 Windows \u684c\u9762\u56fe\u5c42\u5931\u8d25\uff0c\u5df2\u7acb\u5373\u7ec8\u6b62\u58c1\u7eb8\u8fdb\u7a0b\"}";
            }

            _wpHwnd = targetHwnd;
            _wpMode = cleanMode;
            _beamMode = effBeam;
            _wpActive = true;
            _lastOccludedState = false;

            StartRawInputIfNeeded();

            // Two lightweight lock-safe settle checks (read-only diff; zero 0x052C / COM spam)
            IntPtr pinnedTarget = targetHwnd;
            Thread repinThread = new Thread(delegate() {
                int[] delays = new int[] { 400, 1500 };
                foreach (int dMs in delays) {
                    Thread.Sleep(dMs);
                    if (!_wpActive || _wpHwnd != pinnedTarget) return;
                    PeriodicWallpaperHealthCheck();
                }
            });
            repinThread.IsBackground = true;
            repinThread.Start();

            return BuildStatusJson(true);
        }
    }

    private static string DisableWallpaperInternal()
    {
        lock (_wpLock) {
            _wpActive = false;
            DetachAndCloseExisting(true);
            return BuildStatusJson(true);
        }
    }

    private static void ShutdownCleanup()
    {
        if (_shuttingDown) return;
        _shuttingDown = true;
        try { DisableWallpaperInternal(); } catch { }
        try { StopRawInput(); } catch { }
    }

    private static string BuildStatusJson(bool ok)
    {
        if (_wpActive && !IsValidTrackedWallpaperHwnd(_wpHwnd)) {
            _wpHwnd = IntPtr.Zero;
            _wpActive = false;
            StopRawInput();
        }
        JavaScriptSerializer jss = new JavaScriptSerializer();
        Dictionary<string, object> d = new Dictionary<string, object>();
        d["type"] = "ophanim_wallpaper_status";
        d["ok"] = ok;
        d["active"] = _wpActive;
        d["wallpaperMode"] = _wpMode;
        d["beamMode"] = _beamMode;
        d["originalWallpaper"] = _origWallpaper ?? "";
        return jss.Serialize(d);
    }

    private static IntPtr RawInputWndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam)
    {
        if (msg == WM_INPUT && _wpActive && lParam != IntPtr.Zero && _rawInputBuf != IntPtr.Zero) {
            try {
                uint dwSize = (uint)_rawInputBufSize;
                uint hdrSize = (uint)Marshal.SizeOf(typeof(RAWINPUTHEADER));
                uint ret = GetRawInputData(lParam, RID_INPUT, _rawInputBuf, ref dwSize, hdrSize);
                if (ret != unchecked((uint)-1) && ret >= hdrSize + 24) {
                    uint dwType = unchecked((uint)Marshal.ReadInt32(_rawInputBuf, 0));
                    if (dwType == RIM_TYPEMOUSE) {
                        int mOff = (int)hdrSize;
                        ushort btnFlags = unchecked((ushort)Marshal.ReadInt16(_rawInputBuf, mOff + 4));
                        short btnData = Marshal.ReadInt16(_rawInputBuf, mOff + 6);
                        if ((btnFlags & RI_MOUSE_WHEEL) != 0 && btnData != 0) {
                            Interlocked.Add(ref _wheelDeltaRaw, (int)btnData);
                        }
                        ushort primaryDown = _mouseButtonsSwapped ? RI_MOUSE_RIGHT_BUTTON_DOWN : RI_MOUSE_LEFT_BUTTON_DOWN;
                        ushort primaryUp = _mouseButtonsSwapped ? RI_MOUSE_RIGHT_BUTTON_UP : RI_MOUSE_LEFT_BUTTON_UP;
                        if ((btnFlags & primaryDown) != 0) {
                            POINT pt;
                            if (GetCursorPos(out pt)) {
                                Interlocked.Exchange(ref _ldownX, pt.x);
                                Interlocked.Exchange(ref _ldownY, pt.y);
                                Interlocked.Exchange(ref _ldownTicks, Stopwatch.GetTimestamp());
                                Interlocked.Exchange(ref _hasLdown, 1);
                            }
                        }
                        if ((btnFlags & primaryUp) != 0) {
                            if (Interlocked.Exchange(ref _hasLdown, 0) == 1) {
                                POINT pt;
                                if (GetCursorPos(out pt)) {
                                    int dx = pt.x - Interlocked.CompareExchange(ref _ldownX, 0, 0);
                                    int dy = pt.y - Interlocked.CompareExchange(ref _ldownY, 0, 0);
                                    long t0 = Interlocked.Read(ref _ldownTicks);
                                    double dt = (double)(Stopwatch.GetTimestamp() - t0) / Stopwatch.Frequency;
                                    if ((dx * dx + dy * dy) <= 100 && dt <= 0.70) {
                                        Interlocked.Exchange(ref _clickPending, 1);
                                    }
                                }
                            }
                        }
                    }
                }
            } catch { }
            return IntPtr.Zero;
        }
        if (msg == WM_CLOSE) {
            DestroyWindow(hWnd);
            return IntPtr.Zero;
        }
        if (msg == WM_DESTROY) {
            PostQuitMessage(0);
            return IntPtr.Zero;
        }
        return DefWindowProcW(hWnd, msg, wParam, lParam);
    }

    private static void StartRawInputIfNeeded()
    {
        lock (_rawInputLock) {
            if (_rawInputThread != null && _rawInputThread.IsAlive) return;
            _mouseButtonsSwapped = (GetSystemMetrics(23) != 0);
            Interlocked.Exchange(ref _wheelDeltaRaw, 0);
            Interlocked.Exchange(ref _clickPending, 0);
            Interlocked.Exchange(ref _hasLdown, 0);

            Thread t = new Thread(delegate() {
                IntPtr hInstance = GetModuleHandleW(null);
                string clsName = "OphanimRawMouseSink_" + Process.GetCurrentProcess().Id + "_" + Environment.TickCount;
                IntPtr msgHwnd = IntPtr.Zero;
                bool classRegistered = false;
                bool rawRegistered = false;

                try {
                    _rawThreadId = GetCurrentThreadId();
                    _rawInputBuf = Marshal.AllocHGlobal(_rawInputBufSize);
                    _rawWndProcRef = new WndProcDelegate(RawInputWndProc);

                    WNDCLASSEXW wc = new WNDCLASSEXW();
                    wc.cbSize = (uint)Marshal.SizeOf(typeof(WNDCLASSEXW));
                    wc.lpfnWndProc = Marshal.GetFunctionPointerForDelegate(_rawWndProcRef);
                    wc.hInstance = hInstance;
                    wc.lpszClassName = clsName;
                    if (RegisterClassExW(ref wc) == 0) return;
                    classRegistered = true;

                    // HWND_MESSAGE = (IntPtr)(-3)
                    msgHwnd = CreateWindowExW(0, clsName, "", 0, 0, 0, 0, 0, new IntPtr(-3), IntPtr.Zero, hInstance, IntPtr.Zero);
                    if (msgHwnd == IntPtr.Zero) return;
                    _rawMsgHwnd = msgHwnd;

                    RAWINPUTDEVICE[] rid = new RAWINPUTDEVICE[1];
                    rid[0].usUsagePage = 0x01; // Generic Desktop Controls
                    rid[0].usUsage = 0x02;     // Mouse
                    rid[0].dwFlags = RIDEV_INPUTSINK;
                    rid[0].hwndTarget = msgHwnd;
                    if (!RegisterRawInputDevices(rid, 1, (uint)Marshal.SizeOf(typeof(RAWINPUTDEVICE)))) return;
                    rawRegistered = true;

                    MSG m;
                    while (_wpActive && GetMessageW(out m, IntPtr.Zero, 0, 0) > 0) {
                        TranslateMessage(ref m);
                        DispatchMessageW(ref m);
                    }
                } catch {
                } finally {
                    if (rawRegistered) {
                        try {
                            RAWINPUTDEVICE[] unreg = new RAWINPUTDEVICE[1];
                            unreg[0].usUsagePage = 0x01;
                            unreg[0].usUsage = 0x02;
                            unreg[0].dwFlags = RIDEV_REMOVE;
                            unreg[0].hwndTarget = IntPtr.Zero;
                            RegisterRawInputDevices(unreg, 1, (uint)Marshal.SizeOf(typeof(RAWINPUTDEVICE)));
                        } catch { }
                    }
                    if (msgHwnd != IntPtr.Zero && IsWindow(msgHwnd)) {
                        try { DestroyWindow(msgHwnd); } catch { }
                    }
                    if (classRegistered) {
                        try { UnregisterClassW(clsName, hInstance); } catch { }
                    }
                    _rawMsgHwnd = IntPtr.Zero;
                    _rawThreadId = 0;
                    if (_rawInputBuf != IntPtr.Zero) {
                        IntPtr b = _rawInputBuf;
                        _rawInputBuf = IntPtr.Zero;
                        Marshal.FreeHGlobal(b);
                    }
                }
            });
            t.IsBackground = true;
            _rawInputThread = t;
            t.Start();
        }
    }

    private static void StopRawInput()
    {
        Thread toJoin = null;
        lock (_rawInputLock) {
            IntPtr h = _rawMsgHwnd;
            uint tid = _rawThreadId;
            if (h != IntPtr.Zero) {
                try { PostMessageW(h, WM_CLOSE, IntPtr.Zero, IntPtr.Zero); } catch { }
            }
            if (tid != 0) {
                try { PostThreadMessageW(tid, WM_QUIT, IntPtr.Zero, IntPtr.Zero); } catch { }
            }
            toJoin = _rawInputThread;
            _rawInputThread = null;
        }
        if (toJoin != null && toJoin.IsAlive && toJoin != Thread.CurrentThread) {
            try { toJoin.Join(500); } catch { }
        }
        Interlocked.Exchange(ref _wheelDeltaRaw, 0);
        Interlocked.Exchange(ref _clickPending, 0);
        Interlocked.Exchange(ref _hasLdown, 0);
    }

    private static bool IsDesktopOccluded(int physW, int physH)
    {
        try {
            int qstate;
            if (SHQueryUserNotificationState(out qstate) == 0) {
                // QUNS_BUSY=2, QUNS_RUNNING_D3D_FULL_SCREEN=3, QUNS_PRESENTATION_MODE=4
                if (qstate == 2 || qstate == 3 || qstate == 4) return true;
            }
        } catch { }

        try {
            IntPtr fg = GetForegroundWindow();
            if (fg != IntPtr.Zero && fg != _wpHwnd && IsWindowVisible(fg) && !IsIconic(fg)) {
                string cls = GetWinClass(fg);
                if (cls != "Progman" && cls != "WorkerW" && cls != "Shell_TrayWnd" && cls != "Shell_SecondaryTrayWnd" && cls != "NotifyIconOverflowWindow") {
                    RECT rc;
                    if (GetWindowRect(fg, out rc)) {
                        int iw = Math.Max(0, Math.Min(rc.right, physW) - Math.Max(rc.left, 0));
                        int ih = Math.Max(0, Math.Min(rc.bottom, physH) - Math.Max(rc.top, 0));
                        double coverage = ((double)iw * (double)ih) / Math.Max(1.0, (double)physW * (double)physH);
                        if (coverage >= 0.92) return true;
                    }
                }
            }
        } catch { }
        return false;
    }

    private static bool HasWallpaperWsClients()
    {
        lock (_wsLock) {
            for (int i = 0; i < _wsClients.Count; i++) {
                if (_wsClients[i].IsWallpaper) return true;
            }
            return false;
        }
    }

    private static void StartPointerBroadcastLoop()
    {
        Thread t = new Thread(delegate() {
            Stopwatch healthSw = Stopwatch.StartNew();
            Stopwatch occSw = Stopwatch.StartNew();
            Stopwatch idleSw = Stopwatch.StartNew();
            bool hasLastPtr = false;
            int lastPx = int.MinValue, lastPy = int.MinValue, lastBtn = -1;
            bool lastDesk = false;
            bool lastOccluded = false;
            bool initializedOcc = false;

            while (!_shuttingDown) {
                try {
                    if (!_wpActive) {
                        hasLastPtr = false;
                        initializedOcc = false;
                        Thread.Sleep(250);
                        continue;
                    }

                    // Periodic health check every 12s (read-only diff under Monitor.TryEnter(_wpLock))
                    if (healthSw.ElapsedMilliseconds >= 12000) {
                        healthSw.Restart();
                        PeriodicWallpaperHealthCheck();
                        if (!_wpActive) continue;
                    }

                    if (!HasWallpaperWsClients()) {
                        Thread.Sleep(250);
                        continue;
                    }

                    int pw = Math.Max(800, GetSystemMetrics(0));
                    int ph = Math.Max(600, GetSystemMetrics(1));

                    if (!initializedOcc || occSw.ElapsedMilliseconds >= 250) {
                        occSw.Restart();
                        bool occNow = IsDesktopOccluded(pw, ph);
                        if (!initializedOcc || occNow != lastOccluded) {
                            initializedOcc = true;
                            lastOccluded = occNow;
                            _lastOccludedState = occNow;
                            BroadcastWs(occNow ? "{\"type\":\"wp_visibility\",\"occluded\":true}" : "{\"type\":\"wp_visibility\",\"occluded\":false}", true);
                        }
                    }

                    if (lastOccluded) {
                        // Drain queued wheel/click events while occluded so stale clicks don't fire on resume
                        Interlocked.Exchange(ref _wheelDeltaRaw, 0);
                        Interlocked.Exchange(ref _clickPending, 0);
                        hasLastPtr = false;
                        Thread.Sleep(250); // ~4Hz when occluded
                        continue;
                    }

                    POINT pt;
                    if (GetCursorPos(out pt)) {
                        RECT rc;
                        double nx, ny;
                        if (_wpHwnd != IntPtr.Zero && GetWindowRect(_wpHwnd, out rc) && (rc.right - rc.left) >= 200) {
                            nx = (double)(pt.x - rc.left) / (rc.right - rc.left);
                            ny = (double)(pt.y - rc.top) / (rc.bottom - rc.top);
                        } else {
                            nx = (double)pt.x / pw;
                            ny = (double)pt.y / ph;
                        }
                        if (nx < 0) nx = 0; else if (nx > 1) nx = 1;
                        if (ny < 0) ny = 0; else if (ny > 1) ny = 1;

                        IntPtr hAt = WindowFromPoint(pt);
                        bool onDesk = false;
                        if (hAt != IntPtr.Zero) {
                            string clsAt = GetWinClass(hAt);
                            IntPtr root = GetAncestor(hAt, 2);
                            if (root == IntPtr.Zero) root = hAt;
                            string clsRoot = GetWinClass(root);
                            if (clsRoot == "Progman") onDesk = true;
                            else if (clsRoot == "WorkerW" && (clsAt == "SysListView32" || clsAt == "SHELLDLL_DefView" || clsAt == "WorkerW")) {
                                if (FindWindowExW(root, IntPtr.Zero, "SHELLDLL_DefView", null) != IntPtr.Zero) onDesk = true;
                            }
                        }

                        bool swapped = GetSystemMetrics(23) != 0;
                        _mouseButtonsSwapped = swapped;
                        int vkL = swapped ? 0x02 : 0x01;
                        int vkR = swapped ? 0x01 : 0x02;
                        int btn = 0;
                        if ((GetAsyncKeyState(vkL) & 0x8000) != 0) btn |= 1;
                        if ((GetAsyncKeyState(vkR) & 0x8000) != 0) btn |= 2;
                        if ((GetAsyncKeyState(0x04) & 0x8000) != 0) btn |= 4;

                        int rawWheel = Interlocked.Exchange(ref _wheelDeltaRaw, 0);
                        bool clk = (Interlocked.Exchange(ref _clickPending, 0) != 0);
                        double wh = Math.Max(-12.0, Math.Min(12.0, rawWheel / 120.0));
                        double wheelOut = (onDesk && (btn & 4) != 0 && Math.Abs(wh) > 0.01) ? Math.Round(wh, 3) : 0.0;
                        int clickOut = (clk && onDesk) ? 1 : 0;

                        bool changed = !hasLastPtr ||
                                       pt.x != lastPx || pt.y != lastPy ||
                                       btn != lastBtn || onDesk != lastDesk ||
                                       wheelOut != 0.0 || clickOut != 0;

                        if (changed) {
                            hasLastPtr = true;
                            lastPx = pt.x;
                            lastPy = pt.y;
                            lastBtn = btn;
                            lastDesk = onDesk;
                            idleSw.Restart();

                            string json = string.Format(
                                System.Globalization.CultureInfo.InvariantCulture,
                                "{{\"type\":\"wp_ptr\",\"nx\":{0:F5},\"ny\":{1:F5},\"px\":{2},\"py\":{3},\"btn\":{4},\"desk\":{5},\"icon\":false,\"wheel\":{6:F3},\"click\":{7}}}",
                                nx, ny, pt.x, pt.y, btn, onDesk ? "true" : "false", wheelOut, clickOut
                            );
                            BroadcastWs(json, true);
                            Thread.Sleep(33); // ~30Hz active on desktop
                        } else {
                            // Back off to ~4Hz when cursor is idle
                            Thread.Sleep(idleSw.ElapsedMilliseconds >= 500 ? 250 : 33);
                        }
                    } else {
                        Thread.Sleep(120);
                    }
                } catch {
                    Thread.Sleep(120);
                }
            }
        });
        t.IsBackground = true;
        t.Start();
    }

    private static byte[] EncodeWsTextFrame(string text)
    {
        byte[] payload = Encoding.UTF8.GetBytes(text);
        int hdrLen = payload.Length < 126 ? 2 : (payload.Length <= 65535 ? 4 : 10);
        byte[] arr = new byte[hdrLen + payload.Length];
        arr[0] = 0x81;
        if (payload.Length < 126) {
            arr[1] = (byte)payload.Length;
        } else if (payload.Length <= 65535) {
            arr[1] = 126;
            arr[2] = (byte)((payload.Length >> 8) & 0xFF);
            arr[3] = (byte)(payload.Length & 0xFF);
        } else {
            arr[1] = 127;
            long len = payload.Length;
            for (int i = 0; i < 8; i++) arr[2 + i] = (byte)((len >> (8 * (7 - i))) & 0xFF);
        }
        Buffer.BlockCopy(payload, 0, arr, hdrLen, payload.Length);
        return arr;
    }

    private static bool SendWsFrame(WsClientEntry entry, string text)
    {
        if (entry == null) return false;
        byte[] arr = EncodeWsTextFrame(text);
        return SendWsRawBytes(entry, arr);
    }

    private static bool SendWsRawBytes(WsClientEntry entry, byte[] data)
    {
        if (entry == null || data == null) return false;
        lock (entry.WriteLock) {
            try {
                entry.Stream.Write(data, 0, data.Length);
                entry.Stream.Flush();
                return true;
            } catch {
                return false;
            }
        }
    }

    private static void BroadcastWs(string text, bool wallpaperOnly)
    {
        WsClientEntry[] snapshot;
        lock (_wsLock) {
            if (_wsClients.Count == 0) return;
            snapshot = _wsClients.ToArray();
        }
        byte[] frame = EncodeWsTextFrame(text);
        List<WsClientEntry> dead = null;
        for (int i = 0; i < snapshot.Length; i++) {
            WsClientEntry c = snapshot[i];
            if (wallpaperOnly && !c.IsWallpaper) continue;
            if (!SendWsRawBytes(c, frame)) {
                if (dead == null) dead = new List<WsClientEntry>();
                dead.Add(c);
            }
        }
        if (dead != null) {
            lock (_wsLock) {
                for (int i = 0; i < dead.Count; i++) {
                    try { dead[i].Stream.Close(); } catch { }
                    _wsClients.Remove(dead[i]);
                }
            }
        }
    }

    private static string ReadWsTextMessage(WsClientEntry entry)
    {
        Stream s = entry.Stream;
        int b0 = s.ReadByte();
        if (b0 < 0) return null;
        int opcode = b0 & 0x0F;
        if (opcode == 0x8) return null;
        int b1 = s.ReadByte();
        if (b1 < 0) return null;
        bool masked = (b1 & 0x80) != 0;
        long len = b1 & 0x7F;
        if (len == 126) {
            int hi = s.ReadByte(); int lo = s.ReadByte();
            if (hi < 0 || lo < 0) return null;
            len = (hi << 8) | lo;
        } else if (len == 127) {
            len = 0;
            for (int i = 0; i < 8; i++) {
                int bt = s.ReadByte();
                if (bt < 0) return null;
                len = (len << 8) | (uint)bt;
            }
        }
        if (len > 4 * 1024 * 1024) return null;
        byte[] mask = new byte[4];
        if (masked) {
            int r = 0;
            while (r < 4) {
                int n = s.Read(mask, r, 4 - r);
                if (n <= 0) return null;
                r += n;
            }
        }
        byte[] data = new byte[len];
        int readTotal = 0;
        while (readTotal < len) {
            int n = s.Read(data, readTotal, (int)len - readTotal);
            if (n <= 0) return null;
            readTotal += n;
        }
        if (masked) {
            for (int i = 0; i < data.Length; i++) data[i] = (byte)(data[i] ^ mask[i & 3]);
        }
        if (opcode == 0x9) {
            SendWsRawBytes(entry, new byte[] { 0x8A, 0x00 });
            return "";
        }
        return opcode == 0x1 ? Encoding.UTF8.GetString(data) : "";
    }

    private static void SaveConfigObject(object cfgObj)
    {
        if (cfgObj == null) return;
        try {
            JavaScriptSerializer jss = new JavaScriptSerializer();
            jss.MaxJsonLength = 8 * 1024 * 1024;
            string raw = jss.Serialize(cfgObj);
            Directory.CreateDirectory(_cacheDir);
            File.WriteAllText(_configPath, raw, Encoding.UTF8);
            Dictionary<string, object> msg = new Dictionary<string, object>();
            msg["type"] = "ophanim_config_updated";
            msg["config"] = cfgObj;
            BroadcastWs(jss.Serialize(msg), false);
        } catch { }
    }

    private static string HandleWallpaperRequestJson(string bodyJson)
    {
        _wallpaperApiTouched = true;
        JavaScriptSerializer jss = new JavaScriptSerializer();
        jss.MaxJsonLength = 8 * 1024 * 1024;
        Dictionary<string, object> body = jss.Deserialize<Dictionary<string, object>>(string.IsNullOrEmpty(bodyJson) ? "{}" : bodyJson);
        if (body == null) body = new Dictionary<string, object>();

        if (body.ContainsKey("config") && body["config"] != null) {
            SaveConfigObject(body["config"]);
        }

        string action = body.ContainsKey("action") && body["action"] != null ? body["action"].ToString().Trim().ToLowerInvariant() : "status";
        string wpMode = body.ContainsKey("wallpaperMode") && body["wallpaperMode"] != null ? body["wallpaperMode"].ToString().Trim() : "agy_live";
        string beamMode = body.ContainsKey("beamMode") && body["beamMode"] != null ? body["beamMode"].ToString().Trim() : "ambient";

        string resJson;
        if (action == "enable") resJson = EnableWallpaperInternal(wpMode, beamMode);
        else if (action == "disable") resJson = DisableWallpaperInternal();
        else resJson = BuildStatusJson(true);

        BroadcastWs(resJson, false);
        return resJson;
    }

    private static bool IsValidPortString(string portStr)
    {
        int p;
        return int.TryParse(portStr, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out p) && p >= 1 && p <= 65535;
    }

    private static bool IsLoopbackHost(string hostHeader)
    {
        if (string.IsNullOrEmpty(hostHeader)) return false;
        string h = hostHeader.Trim().ToLowerInvariant();
        if (h.StartsWith("[")) {
            int end = h.IndexOf(']');
            if (end < 0) return false;
            string ip = h.Substring(0, end + 1);
            if (ip != "[::1]") return false;
            if (end == h.Length - 1) return true;
            if (h[end + 1] != ':') return false;
            return IsValidPortString(h.Substring(end + 2));
        }
        int col = h.IndexOf(':');
        if (col >= 0) {
            if (h.IndexOf(':', col + 1) >= 0) return false;
            string name = h.Substring(0, col);
            if (name != "127.0.0.1" && name != "localhost") return false;
            return IsValidPortString(h.Substring(col + 1));
        }
        return h == "127.0.0.1" || h == "localhost";
    }

    private static bool ValidateOriginHeader(string originRaw, out string allowOrigin)
    {
        allowOrigin = null;
        if (string.IsNullOrEmpty(originRaw)) return true;
        string orig = originRaw.Trim();
        if (orig.Length == 0) return true;
        if (orig.IndexOf('\r') >= 0 || orig.IndexOf('\n') >= 0) return false;
        string lower = orig.ToLowerInvariant();
        if (lower == "null" || lower.StartsWith("file://")) {
            allowOrigin = orig;
            return true;
        }
        Uri uri;
        if (Uri.TryCreate(orig, UriKind.Absolute, out uri)) {
            if (uri.Scheme == "http" || uri.Scheme == "https") {
                string uh = uri.DnsSafeHost.ToLowerInvariant();
                IPAddress parsedIp;
                if (uh == "localhost" || uh == "127.0.0.1" || uh == "::1" ||
                    (IPAddress.TryParse(uh, out parsedIp) && (parsedIp.Equals(IPAddress.Loopback) || parsedIp.Equals(IPAddress.IPv6Loopback)))) {
                    allowOrigin = orig;
                    return true;
                }
            }
        }
        return false;
    }

    private static void WriteHttpResponse(Stream s, int code, string statusText, string contentType, byte[] bodyBytes, string allowOrigin)
    {
        if (bodyBytes == null) bodyBytes = new byte[0];
        StringBuilder hdr = new StringBuilder();
        hdr.AppendFormat("HTTP/1.1 {0} {1}\r\n", code, statusText);
        hdr.AppendFormat("Content-Type: {0}\r\n", contentType);
        hdr.AppendFormat("Content-Length: {0}\r\n", bodyBytes.Length);
        hdr.Append("Cache-Control: no-store, no-cache, must-revalidate\r\n");
        if (!string.IsNullOrEmpty(allowOrigin)) {
            hdr.AppendFormat("Access-Control-Allow-Origin: {0}\r\n", allowOrigin);
            hdr.Append("Vary: Origin\r\n");
            hdr.Append("Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n");
            hdr.Append("Access-Control-Allow-Headers: Content-Type, X-Ophanim-Token\r\n");
            hdr.Append("Access-Control-Allow-Private-Network: true\r\n");
        }
        hdr.Append("Connection: close\r\n\r\n");
        byte[] hb = Encoding.ASCII.GetBytes(hdr.ToString());
        s.Write(hb, 0, hb.Length);
        if (bodyBytes.Length > 0) s.Write(bodyBytes, 0, bodyBytes.Length);
        s.Flush();
    }

    private static void HandleClient(TcpClient client)
    {
        try {
            using (NetworkStream ns = client.GetStream()) {
                ns.ReadTimeout = 15000;
                List<byte> hdrBuf = new List<byte>();
                int b;
                while ((b = ns.ReadByte()) >= 0) {
                    hdrBuf.Add((byte)b);
                    int cnt = hdrBuf.Count;
                    if (cnt >= 4 && hdrBuf[cnt - 4] == 13 && hdrBuf[cnt - 3] == 10 && hdrBuf[cnt - 2] == 13 && hdrBuf[cnt - 1] == 10) break;
                    if (cnt > 32768) return;
                }
                if (hdrBuf.Count < 4) return;

                string hdrStr = Encoding.ASCII.GetString(hdrBuf.ToArray());
                string[] lines = hdrStr.Split(new string[] { "\r\n" }, StringSplitOptions.RemoveEmptyEntries);
                if (lines.Length == 0) return;

                string[] reqParts = lines[0].Split(' ');
                if (reqParts.Length < 2) return;
                string method = reqParts[0].ToUpperInvariant();
                string rawTarget = reqParts[1];
                string pathOnly = rawTarget.Split('?')[0];

                Dictionary<string, string> headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                for (int i = 1; i < lines.Length; i++) {
                    int col = lines[i].IndexOf(':');
                    if (col > 0) headers[lines[i].Substring(0, col).Trim()] = lines[i].Substring(col + 1).Trim();
                }

                // Loopback Host validation (DNS rebinding defense)
                string hostHdr = headers.ContainsKey("Host") ? headers["Host"] : "";
                if (!IsLoopbackHost(hostHdr)) {
                    WriteHttpResponse(ns, 403, "Forbidden", "application/json", Encoding.UTF8.GetBytes("{\"ok\":false,\"error\":\"invalid_host\"}"), null);
                    return;
                }

                // Validated Origin check (no wildcard '*')
                string origHdr = headers.ContainsKey("Origin") ? headers["Origin"] : null;
                string allowOrigin;
                if (!ValidateOriginHeader(origHdr, out allowOrigin)) {
                    WriteHttpResponse(ns, 403, "Forbidden", "application/json", Encoding.UTF8.GetBytes("{\"ok\":false,\"error\":\"invalid_origin\"}"), null);
                    return;
                }

                if (method == "OPTIONS") {
                    WriteHttpResponse(ns, 204, "No Content", "text/plain", new byte[0], allowOrigin);
                    return;
                }

                if (method == "GET" && pathOnly == "/ws" && headers.ContainsKey("Sec-WebSocket-Key")) {
                    string wsKey = headers["Sec-WebSocket-Key"].Trim() + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
                    string acceptKey;
                    using (SHA1 sha1 = SHA1.Create()) {
                        acceptKey = Convert.ToBase64String(sha1.ComputeHash(Encoding.ASCII.GetBytes(wsKey)));
                    }
                    string hs = "HTTP/1.1 101 Switching Protocols\r\n" +
                                "Upgrade: websocket\r\n" +
                                "Connection: Upgrade\r\n" +
                                "Sec-WebSocket-Accept: " + acceptKey + "\r\n\r\n";
                    byte[] hsb = Encoding.ASCII.GetBytes(hs);
                    ns.Write(hsb, 0, hsb.Length);
                    ns.Flush();
                    ns.ReadTimeout = Timeout.Infinite;

                    bool isWpClient = rawTarget.IndexOf("wallpaper=1", StringComparison.OrdinalIgnoreCase) >= 0;
                    WsClientEntry entry = new WsClientEntry(ns, isWpClient);
                    lock (_wsLock) { _wsClients.Add(entry); }
                    try {
                        SendWsFrame(entry, BuildStatusJson(true));
                        if (entry.IsWallpaper) {
                            SendWsFrame(entry, _lastOccludedState ? "{\"type\":\"wp_visibility\",\"occluded\":true}" : "{\"type\":\"wp_visibility\",\"occluded\":false}");
                        }
                        if (File.Exists(_configPath)) {
                            string savedRaw = File.ReadAllText(_configPath, Encoding.UTF8);
                            if (!string.IsNullOrEmpty(savedRaw)) {
                                SendWsFrame(entry, "{\"type\":\"ophanim_config_updated\",\"config\":" + savedRaw + "}");
                            }
                        }
                        JavaScriptSerializer jss = new JavaScriptSerializer();
                        jss.MaxJsonLength = 8 * 1024 * 1024;
                        while (true) {
                            string msg = ReadWsTextMessage(entry);
                            if (msg == null) break;
                            if (msg.Length == 0) continue;
                            try {
                                Dictionary<string, object> payload = jss.Deserialize<Dictionary<string, object>>(msg);
                                if (payload == null || !payload.ContainsKey("type")) continue;
                                string t = payload["type"] != null ? payload["type"].ToString() : "";
                                if (t == "ophanim_wallpaper_action") {
                                    HandleWallpaperRequestJson(msg);
                                } else if (t == "ophanim_save_config" && payload.ContainsKey("config")) {
                                    SaveConfigObject(payload["config"]);
                                } else if (t == "ophanim_live_state_sync" && payload.ContainsKey("config")) {
                                    Dictionary<string, object> upd = new Dictionary<string, object>();
                                    upd["type"] = "ophanim_config_updated";
                                    upd["config"] = payload["config"];
                                    BroadcastWs(jss.Serialize(upd), false);
                                } else if (t == "ophanim_preview_completion" || t == "ophanim_ack_completions") {
                                    BroadcastWs(msg, false);
                                } else if (t == "ophanim_wallpaper_hello") {
                                    entry.IsWallpaper = true;
                                    SendWsFrame(entry, BuildStatusJson(true));
                                    SendWsFrame(entry, _lastOccludedState ? "{\"type\":\"wp_visibility\",\"occluded\":true}" : "{\"type\":\"wp_visibility\",\"occluded\":false}");
                                    if (File.Exists(_configPath)) {
                                        string sr = File.ReadAllText(_configPath, Encoding.UTF8);
                                        if (!string.IsNullOrEmpty(sr)) SendWsFrame(entry, "{\"type\":\"ophanim_config_updated\",\"config\":" + sr + "}");
                                    }
                                }
                            } catch { }
                        }
                    } finally {
                        lock (_wsLock) { _wsClients.Remove(entry); }
                    }
                    return;
                }

                int contentLen = 0;
                if (headers.ContainsKey("Content-Length")) int.TryParse(headers["Content-Length"], out contentLen);
                string bodyStr = "";
                if (contentLen > 0 && contentLen < 8 * 1024 * 1024) {
                    byte[] bodyBytes = new byte[contentLen];
                    int got = 0;
                    while (got < contentLen) {
                        int n = ns.Read(bodyBytes, got, contentLen - got);
                        if (n <= 0) break;
                        got += n;
                    }
                    bodyStr = Encoding.UTF8.GetString(bodyBytes, 0, got);
                }

                if (pathOnly == "/api/health") {
                    WriteHttpResponse(ns, 200, "OK", "application/json; charset=utf-8",
                        Encoding.UTF8.GetBytes("{\"ok\":true,\"service\":\"ophanim_toy_native\",\"interactiveWallpaper\":true}"), allowOrigin);
                    return;
                }
                if (pathOnly == "/api/shutdown" && method == "POST") {
                    WriteHttpResponse(ns, 200, "OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes("{\"ok\":true}"), allowOrigin);
                    ThreadPool.QueueUserWorkItem(delegate(object o) {
                        Thread.Sleep(120);
                        ShutdownCleanup();
                        Environment.Exit(0);
                    });
                    return;
                }
                if (pathOnly == "/api/wallpaper") {
                    string res = (method == "POST") ? HandleWallpaperRequestJson(bodyStr) : BuildStatusJson(true);
                    WriteHttpResponse(ns, 200, "OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes(res), allowOrigin);
                    return;
                }
                if (pathOnly == "/api/save-config" && method == "POST") {
                    JavaScriptSerializer jss = new JavaScriptSerializer();
                    jss.MaxJsonLength = 8 * 1024 * 1024;
                    Dictionary<string, object> d = jss.Deserialize<Dictionary<string, object>>(bodyStr);
                    if (d != null && d.ContainsKey("config")) SaveConfigObject(d["config"]);
                    WriteHttpResponse(ns, 200, "OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes("{\"ok\":true}"), allowOrigin);
                    return;
                }
                if (pathOnly == "/" || pathOnly == "/ophanim_toy_sanctum.html") {
                    if (File.Exists(_htmlPath)) {
                        string htmlText = File.ReadAllText(_htmlPath, Encoding.UTF8);
                        if (rawTarget.IndexOf("wallpaper=1", StringComparison.OrdinalIgnoreCase) >= 0) {
                            htmlText = htmlText.Replace("<title>OPHANIM TOY SANCTUM</title>", "<title>OPHANIM WALLPAPER</title>");
                            htmlText = htmlText.Replace("<title>OPHANIM UI</title>", "<title>OPHANIM WALLPAPER</title>");
                        }
                        byte[] htmlBytes = Encoding.UTF8.GetBytes(htmlText);
                        WriteHttpResponse(ns, 200, "OK", "text/html; charset=utf-8", htmlBytes, allowOrigin);
                        return;
                    }
                }
                WriteHttpResponse(ns, 404, "Not Found", "text/plain", Encoding.ASCII.GetBytes("Not Found"), allowOrigin);
            }
        } catch {
        } finally {
            try { client.Close(); } catch { }
        }
    }

    public static void StartServer(string htmlPath, string cacheDir, string browserExe, int port, bool openWindowInitially, string appUrl)
    {
        EnableDpiAwarenessSafe();
        _htmlPath = htmlPath;
        _cacheDir = cacheDir;
        _configPath = Path.Combine(cacheDir, "toy_saved_config.json");
        _browserExe = browserExe;
        _port = port;
        Directory.CreateDirectory(cacheDir);

        AppDomain.CurrentDomain.ProcessExit += delegate(object sender, EventArgs e) {
            ShutdownCleanup();
        };
        try {
            Console.CancelKeyPress += delegate(object sender, ConsoleCancelEventArgs e) {
                ShutdownCleanup();
            };
        } catch { }

        TcpListener listener = new TcpListener(IPAddress.Loopback, port);
        try { listener.Server.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true); } catch { }
        listener.Start();

        StartPointerBroadcastLoop();

        if (openWindowInitially && !string.IsNullOrEmpty(browserExe) && File.Exists(browserExe)) {
            Thread winOpenThread = new Thread(delegate() {
                // Grace period: if an already-open `file:///.../ophanim_toy_sanctum.html` tab is polling `/api/health`
                // after the user clicked [\u8bbe\u4e3a\u58c1\u7eb8], let it immediately set the wallpaper without popping up a duplicate window!
                Thread.Sleep(850);
                if (_wallpaperApiTouched || _wpActive) return;
                try {
                    string appProf = Path.Combine(cacheDir, "toy_app_window");
                    Directory.CreateDirectory(appProf);
                    using (Process p = Process.Start(browserExe, string.Format(
                        "--user-data-dir=\"{0}\" --app=\"{1}\" --window-size=1560,940 --force-dark-mode --no-first-run --no-default-browser-check --disable-features=Translate,EdgeSidebar,msEdgeSidebarV2",
                        appProf, appUrl
                    ))) { }
                } catch { }
            });
            winOpenThread.IsBackground = true;
            winOpenThread.Start();
        }

        Thread idleMonitor = new Thread(delegate() {
            int idleSec = 0;
            Thread.Sleep(30000);
            while (!_shuttingDown) {
                Thread.Sleep(5000);
                int clientsNow;
                lock (_wsLock) { clientsNow = _wsClients.Count; }
                if (!_wpActive && clientsNow == 0) {
                    idleSec += 5;
                    if (idleSec >= 180) {
                        ShutdownCleanup();
                        Environment.Exit(0);
                    }
                } else {
                    idleSec = 0;
                }
            }
        });
        idleMonitor.IsBackground = true;
        idleMonitor.Start();

        while (!_shuttingDown) {
            TcpClient c = listener.AcceptTcpClient();
            ThreadPool.QueueUserWorkItem(delegate(object st) { HandleClient((TcpClient)st); }, c);
        }
    }
}
'@

# 2. Cache compiled C# assembly to `.ophanim_toy_cache\OphanimToyHost_<hash>.dll` for <150ms instant startup!
Add-Type -AssemblyName 'System.Web.Extensions'
$sha = [System.Security.Cryptography.SHA1]::Create()
$hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($CsSource))
$hashHex = ([System.BitConverter]::ToString($hashBytes) -replace '-', '').Substring(0, 12)
$CachedDll = Join-Path $CacheDir ("OphanimToyHost_" + $hashHex + ".dll")

$LoadedOk = $false
if (Test-Path -LiteralPath $CachedDll) {
    try {
        Add-Type -Path $CachedDll -ErrorAction Stop
        $LoadedOk = $true
    } catch {
        $LoadedOk = $false
    }
}
if (-not $LoadedOk) {
    try {
        Add-Type -ReferencedAssemblies @('System.dll', 'System.Core.dll', 'System.Web.Extensions.dll') -TypeDefinition $CsSource -OutputAssembly $CachedDll -ErrorAction Stop
        Add-Type -Path $CachedDll -ErrorAction Stop
    } catch {
        Add-Type -ReferencedAssemblies @('System.dll', 'System.Core.dll', 'System.Web.Extensions.dll') -TypeDefinition $CsSource
    }
}

$BrowserExe = Find-ChromiumExe
[OphanimToyNativeHost]::StartServer($HtmlFile, $CacheDir, $BrowserExe, $Port, (-not $IsWakeOnly), $AppUrl)
