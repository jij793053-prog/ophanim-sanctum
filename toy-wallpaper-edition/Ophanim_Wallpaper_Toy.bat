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
using System.Management;
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

    [StructLayout(LayoutKind.Sequential)]
    public struct MSLLHOOKSTRUCT { public POINT pt; public uint mouseData; public uint flags; public uint time; public IntPtr dwExtraInfo; }

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    public delegate IntPtr LowLevelMouseProc(int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindowW(string cls, string title);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindowExW(IntPtr parent, IntPtr after, string cls, string title);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc fn, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc fn, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassNameW(IntPtr hWnd, StringBuilder sb, int max);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder sb, int max);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr SetParent(IntPtr child, IntPtr newParent);
    [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool EnableWindow(IntPtr hWnd, bool enable);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    [DllImport("user32.dll")] public static extern bool ScreenToClient(IntPtr hWnd, ref POINT lpPoint);
    [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
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
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern bool SystemParametersInfoW(uint action, uint param, string pvParam, uint winIni);
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
    [DllImport("user32.dll")] public static extern IntPtr SetWindowsHookExW(int idHook, LowLevelMouseProc lpfn, IntPtr hMod, uint threadId);
    [DllImport("user32.dll")] public static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool UnhookWindowsHookEx(IntPtr hhk);
    [DllImport("user32.dll")] public static extern int GetMessageW(out MSG lpMsg, IntPtr hWnd, uint min, uint max);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint procId);

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

    private static string _htmlPath;
    private static string _cacheDir;
    private static string _configPath;
    private static string _browserExe;
    private static int _port = 18791;

    private static readonly object _wsLock = new object();
    private static readonly List<Stream> _wsClients = new List<Stream>();
    private static readonly object _wpLock = new object();

    private static volatile bool _wpActive = false;
    private static volatile bool _wallpaperApiTouched = false;
    private static string _wpMode = "agy_live";
    private static string _beamMode = "ambient";
    private static string _origWallpaper = "";
    private static IntPtr _wpHwnd = IntPtr.Zero;
    private static readonly List<int> _spawnedWpPids = new List<int>();

    private static readonly object _hookLock = new object();
    private static double _wheelAccum = 0.0;
    private static bool _clickPending = false;
    private static int _ldownX = 0, _ldownY = 0;
    private static long _ldownTicks = 0;
    private static bool _hasLdown = false;
    private static LowLevelMouseProc _hookRef;

    private static void EnableDpiAwarenessSafe()
    {
        try {
            if (SetProcessDpiAwarenessContext(new IntPtr(-4))) return;
        } catch { }
        try { SetProcessDPIAware(); } catch { }
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

    private static void KillToyWallpaperProfileProcesses()
    {
        try {
            using (ManagementObjectSearcher mos = new ManagementObjectSearcher(
                "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='msedge.exe' OR Name='chrome.exe'")) {
                foreach (ManagementObject mo in mos.Get()) {
                    try {
                        string cmd = mo["CommandLine"] != null ? mo["CommandLine"].ToString() : "";
                        if (cmd.IndexOf("toy_wp_profile", StringComparison.OrdinalIgnoreCase) >= 0) {
                            int pid = Convert.ToInt32(mo["ProcessId"]);
                            Process p = Process.GetProcessById(pid);
                            if (!p.HasExited) p.Kill();
                        }
                    } catch { }
                }
            }
        } catch { }
    }

    private static void HideFromTaskbar(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return;
        Thread t = new Thread(delegate() {
            try {
                ITaskbarList tbl = (ITaskbarList)(new CTaskbarList());
                if (tbl.HrInit() == 0) tbl.DeleteTab(hwnd);
                Marshal.ReleaseComObject(tbl);
            } catch { }
        });
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

    private static bool ApplyWallpaperStylesAndZOrder(IntPtr hwnd, int physW, int physH)
    {
        EnableDpiAwarenessSafe();
        if (hwnd == IntPtr.Zero || !IsWindow(hwnd)) return false;

        IntPtr progman = FindWindowW("Progman", null);
        if (progman == IntPtr.Zero) return false;

        IntPtr dummy;
        SendMessageTimeoutW(progman, 0x052C, new IntPtr(0xD), new IntPtr(1), 0, 1000, out dummy);
        SendMessageTimeoutW(progman, 0x052C, IntPtr.Zero, IntPtr.Zero, 0, 1000, out dummy);

        IntPtr defviewInProgman = FindWindowExW(progman, IntPtr.Zero, "SHELLDLL_DefView", null);

        long stripStyle = WS_POPUP | WS_CAPTION | WS_BORDER | WS_DLGFRAME | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU;
        long childFlags = WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN | WS_DISABLED;
        long exStrip = WS_EX_APPWINDOW | WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE;
        long exAdd = WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_NOPARENTNOTIFY | WS_EX_LAYERED;

        if (defviewInProgman != IntPtr.Zero) {
            // Windows 11 24H2+ RaisedDesktop (`SHELLDLL_DefView` & `WorkerW` inside `Progman`)
            IntPtr curParent = GetParent(hwnd);
            long curStyle = GetWinLongSafe(hwnd, GWL_STYLE) & 0xFFFFFFFFL;
            long newStyle = ((curStyle & ~stripStyle) | childFlags) & 0xFFFFFFFFL;
            SetWinLongSafe(hwnd, GWL_STYLE, newStyle);

            long curEx = GetWinLongSafe(hwnd, GWL_EXSTYLE) & 0xFFFFFFFFL;
            long newEx = ((curEx & ~exStrip) | exAdd) & 0xFFFFFFFFL;
            SetWinLongSafe(hwnd, GWL_EXSTYLE, newEx);
            SetLayeredWindowAttributes(hwnd, 0, 255, 0x02);
            EnableWindow(hwnd, false);
            HideFromTaskbar(hwnd);

            if (curParent != progman) {
                SetParent(hwnd, progman);
                SetWinLongSafe(hwnd, GWL_STYLE, newStyle);
                SetWinLongSafe(hwnd, GWL_EXSTYLE, newEx);
                SetLayeredWindowAttributes(hwnd, 0, 255, 0x02);
                EnableWindow(hwnd, false);
                HideFromTaskbar(hwnd);
            }

            POINT pt = new POINT { x = 0, y = 0 };
            ScreenToClient(progman, ref pt);
            SetWindowPos(hwnd, defviewInProgman, pt.x, pt.y, physW, physH, SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW);
            HideFromTaskbar(hwnd);

            IntPtr workerwInProgman = FindWindowExW(progman, IntPtr.Zero, "WorkerW", null);
            if (workerwInProgman != IntPtr.Zero && workerwInProgman != hwnd) {
                SetWindowPos(workerwInProgman, hwnd, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            }
            return true;
        }

        // Classic Windows 10 / Windows 11 <=23H2 `WorkerW` architecture
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

        IntPtr targetParent = wallpaperWorkerW != IntPtr.Zero ? wallpaperWorkerW : progman;
        IntPtr curP = GetParent(hwnd);
        long cStyle = GetWinLongSafe(hwnd, GWL_STYLE) & 0xFFFFFFFFL;
        long nStyle = ((cStyle & ~stripStyle) | childFlags) & 0xFFFFFFFFL;
        SetWinLongSafe(hwnd, GWL_STYLE, nStyle);

        long cEx = GetWinLongSafe(hwnd, GWL_EXSTYLE) & 0xFFFFFFFFL;
        long nEx = ((cEx & ~exStrip) | exAdd) & 0xFFFFFFFFL;
        SetWinLongSafe(hwnd, GWL_EXSTYLE, nEx);
        SetLayeredWindowAttributes(hwnd, 0, 255, 0x02);
        EnableWindow(hwnd, false);
        HideFromTaskbar(hwnd);

        if (curP != targetParent) {
            SetParent(hwnd, targetParent);
            SetWinLongSafe(hwnd, GWL_STYLE, nStyle);
            SetWinLongSafe(hwnd, GWL_EXSTYLE, nEx);
            SetLayeredWindowAttributes(hwnd, 0, 255, 0x02);
            EnableWindow(hwnd, false);
            HideFromTaskbar(hwnd);
        }

        POINT ptClassic = new POINT { x = 0, y = 0 };
        ScreenToClient(targetParent, ref ptClassic);
        SetWindowPos(hwnd, IntPtr.Zero, ptClassic.x, ptClassic.y, physW, physH, SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW);
        HideFromTaskbar(hwnd);
        return true;
    }

    private static void DetachAndCloseExisting(bool restoreStatic)
    {
        List<IntPtr> hwnds = FindWallpaperHwnds();
        if (_wpHwnd != IntPtr.Zero && !hwnds.Contains(_wpHwnd)) hwnds.Add(_wpHwnd);
        foreach (IntPtr h in hwnds) {
            try {
                uint pid = 0;
                GetWindowThreadProcessId(h, out pid);
                ShowWindow(h, 0);
                SetParent(h, IntPtr.Zero);
                PostMessageW(h, 0x0010, IntPtr.Zero, IntPtr.Zero);
                if (pid > 0 && !_spawnedWpPids.Contains((int)pid)) _spawnedWpPids.Add((int)pid);
            } catch { }
        }
        Thread.Sleep(160);
        foreach (int pid in _spawnedWpPids.ToArray()) {
            try {
                Process p = Process.GetProcessById(pid);
                if (!p.HasExited) p.Kill();
            } catch { }
        }
        _spawnedWpPids.Clear();
        KillToyWallpaperProfileProcesses();
        _wpHwnd = IntPtr.Zero;

        if (restoreStatic) {
            if (string.IsNullOrEmpty(_origWallpaper) || !File.Exists(_origWallpaper)) {
                _origWallpaper = ReadSystemWallpaper();
            }
            if (!string.IsNullOrEmpty(_origWallpaper) && File.Exists(_origWallpaper)) {
                SystemParametersInfoW(0x0014, 0, _origWallpaper, 0x01 | 0x02);
            }
            IntPtr progman = FindWindowW("Progman", null);
            if (progman != IntPtr.Zero) {
                RedrawWindow(progman, IntPtr.Zero, IntPtr.Zero, 0x0585);
                IntPtr ww = FindWindowExW(progman, IntPtr.Zero, "WorkerW", null);
                if (ww != IntPtr.Zero) {
                    ShowWindow(ww, 5);
                    RedrawWindow(ww, IntPtr.Zero, IntPtr.Zero, 0x0585);
                }
            }
        }
    }

    public static IntPtr SpawnWallpaperBrowserOnlyForTest(out int procId)
    {
        procId = 0;
        int physW, physH, dipW, dipH;
        GetPrimaryScreenMetrics(out physW, out physH, out dipW, out dipH);
        string wpProfile = Path.Combine(_cacheDir, "toy_wp_profile");
        string wpDiskCache = Path.Combine(_cacheDir, "toy_wp_cache");
        Directory.CreateDirectory(wpProfile);
        Directory.CreateDirectory(wpDiskCache);
        PresetWallpaperProfilePrefs(wpProfile, dipW, dipH);
        KillToyWallpaperProfileProcesses();

        string wpUrl = string.Format(
            "http://127.0.0.1:{0}/ophanim_toy_sanctum.html?ws=ws://127.0.0.1:{0}/ws&wallpaper=1&wpMode=ambient_eco&beamMode=ambient&eco=1&t={1}",
            _port, DateTime.UtcNow.Ticks
        );
        bool isEdge = _browserExe.ToLowerInvariant().Contains("msedge");
        string kioskExtra = isEdge ? "--edge-kiosk-type=fullscreen " : "";
        string args = string.Format(
            "--user-data-dir=\"{0}\" --disk-cache-dir=\"{1}\" --window-position=0,0 --window-size={2},{3} --kiosk \"{4}\" {5}--no-first-run --no-default-browser-check --disable-extensions --disable-sync --disable-infobars --disable-session-crashed-bubble --autoplay-policy=no-user-gesture-required --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-features=CalculateNativeWinOcclusion,Translate,msEdgeSidebarV2",
            wpProfile, wpDiskCache, dipW, dipH, wpUrl, kioskExtra
        );
        ProcessStartInfo psi = new ProcessStartInfo(_browserExe, args);
        psi.UseShellExecute = false;
        Process proc = Process.Start(psi);
        if (proc != null) procId = proc.Id;

        Stopwatch sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < 12000) {
            List<IntPtr> found = FindWallpaperHwnds();
            if (found.Count > 0) return found[0];
            Thread.Sleep(45);
        }
        return IntPtr.Zero;
    }

    private static string EnableWallpaperInternal(string wpMode, string beamMode)
    {
        lock (_wpLock) {
            if (string.IsNullOrEmpty(_browserExe) || !File.Exists(_browserExe)) {
                return "{\"ok\":false,\"active\":false,\"error\":\"\u672a\u627e\u5230 Microsoft Edge \u6216 Chrome \u6d4f\u89c8\u5668\"}";
            }
            IntPtr progmanCheck = FindWindowW("Progman", null);
            if (progmanCheck == IntPtr.Zero) {
                return "{\"ok\":false,\"active\":false,\"error\":\"\u65e0\u6cd5\u5b9a\u4f4d Windows Progman \u684c\u9762\u56fe\u5c42\"}";
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
            string wpUrl = string.Format(
                "http://127.0.0.1:{0}/ophanim_toy_sanctum.html?ws=ws://127.0.0.1:{0}/ws&wallpaper=1&wpMode={1}&beamMode={2}&eco={3}&t={4}",
                _port, Uri.EscapeDataString(cleanMode), Uri.EscapeDataString(effBeam), ecoFlag, DateTime.UtcNow.Ticks
            );

            // IMPORTANT: NEVER pass `--inprivate` with `--kiosk --edge-kiosk-type=fullscreen` (Edge blocks Kiosk in InPrivate!)
            bool isEdge = _browserExe.ToLowerInvariant().Contains("msedge");
            string kioskExtra = isEdge ? "--edge-kiosk-type=fullscreen " : "";
            string args = string.Format(
                "--user-data-dir=\"{0}\" --disk-cache-dir=\"{1}\" --window-position=0,0 --window-size={2},{3} --kiosk \"{4}\" {5}--no-first-run --no-default-browser-check --disable-extensions --disable-sync --disable-infobars --disable-session-crashed-bubble --autoplay-policy=no-user-gesture-required --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-features=CalculateNativeWinOcclusion,Translate,msEdgeSidebarV2",
                wpProfile, wpDiskCache, dipW, dipH, wpUrl, kioskExtra
            );

            ProcessStartInfo psi = new ProcessStartInfo(_browserExe, args);
            psi.UseShellExecute = false;
            Process proc = Process.Start(psi);
            if (proc != null) _spawnedWpPids.Add(proc.Id);

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
                return "{\"ok\":false,\"active\":false,\"error\":\"\u7b49\u5f85\u58c1\u7eb8\u6e32\u67d3\u7a97\u53e3\u8d85\u65f6\uff0c\u8bf7\u91cd\u8bd5\"}";
            }

            if (!ApplyWallpaperStylesAndZOrder(targetHwnd, physW, physH)) {
                DetachAndCloseExisting(true);
                return "{\"ok\":false,\"active\":false,\"error\":\"\u5d4c\u5165 Windows \u684c\u9762\u56fe\u5c42\u5931\u8d25\"}";
            }

            _wpHwnd = targetHwnd;
            _wpMode = cleanMode;
            _beamMode = effBeam;
            _wpActive = true;

            // Delayed re-pin thread so Chromium's post-paint kiosk SetWindowPos never escapes Progman
            IntPtr pinnedTarget = targetHwnd;
            int pW = physW, pH = physH;
            Thread repinThread = new Thread(delegate() {
                int[] delays = new int[] { 250, 650, 1350, 2400 };
                foreach (int dMs in delays) {
                    Thread.Sleep(dMs);
                    if (!_wpActive || _wpHwnd != pinnedTarget || !IsWindow(pinnedTarget)) return;
                    try { ApplyWallpaperStylesAndZOrder(pinnedTarget, pW, pH); } catch { return; }
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

    private static string BuildStatusJson(bool ok)
    {
        if (_wpActive && (_wpHwnd == IntPtr.Zero || !IsWindow(_wpHwnd))) {
            List<IntPtr> f = FindWallpaperHwnds();
            _wpHwnd = f.Count > 0 ? f[0] : IntPtr.Zero;
            if (_wpHwnd == IntPtr.Zero) _wpActive = false;
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

    private static void StartMouseHookThread()
    {
        Thread t = new Thread(delegate() {
            _hookRef = delegate(int nCode, IntPtr wParam, IntPtr lParam) {
                try {
                    if (nCode >= 0 && lParam != IntPtr.Zero && _wpActive) {
                        int msg = wParam.ToInt32();
                        if (msg == 0x020A) { // WM_MOUSEWHEEL
                            if ((GetAsyncKeyState(0x04) & 0x8000) != 0) {
                                MSLLHOOKSTRUCT info = (MSLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(MSLLHOOKSTRUCT));
                                short delta = unchecked((short)((info.mouseData >> 16) & 0xFFFF));
                                if (delta != 0) {
                                    lock (_hookLock) {
                                        _wheelAccum = Math.Max(-12.0, Math.Min(12.0, _wheelAccum + (delta / 120.0)));
                                    }
                                }
                            }
                        } else if (msg == 0x0201) { // WM_LBUTTONDOWN
                            MSLLHOOKSTRUCT info = (MSLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(MSLLHOOKSTRUCT));
                            lock (_hookLock) {
                                _ldownX = info.pt.x;
                                _ldownY = info.pt.y;
                                _ldownTicks = Stopwatch.GetTimestamp();
                                _hasLdown = true;
                            }
                        } else if (msg == 0x0202) { // WM_LBUTTONUP
                            MSLLHOOKSTRUCT info = (MSLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(MSLLHOOKSTRUCT));
                            lock (_hookLock) {
                                if (_hasLdown) {
                                    int dx = info.pt.x - _ldownX;
                                    int dy = info.pt.y - _ldownY;
                                    double dt = (double)(Stopwatch.GetTimestamp() - _ldownTicks) / Stopwatch.Frequency;
                                    _hasLdown = false;
                                    if ((dx * dx + dy * dy) <= 100 && dt <= 0.70) _clickPending = true;
                                }
                            }
                        }
                    }
                } catch { }
                return CallNextHookEx(IntPtr.Zero, nCode, wParam, lParam);
            };
            IntPtr hh = SetWindowsHookExW(14, _hookRef, IntPtr.Zero, 0);
            if (hh == IntPtr.Zero) return;
            MSG m;
            while (GetMessageW(out m, IntPtr.Zero, 0, 0) > 0) { }
            UnhookWindowsHookEx(hh);
        });
        t.IsBackground = true;
        t.Start();
    }

    private static void StartPointerBroadcastLoop()
    {
        Thread t = new Thread(delegate() {
            int pinTick = 0;
            while (true) {
                try {
                    if (!_wpActive || _wsClients.Count == 0) {
                        Thread.Sleep(80);
                        continue;
                    }
                    pinTick++;
                    if (pinTick % 120 == 0 && _wpHwnd != IntPtr.Zero && IsWindow(_wpHwnd)) {
                        int pw, ph, dw, dh;
                        GetPrimaryScreenMetrics(out pw, out ph, out dw, out dh);
                        ApplyWallpaperStylesAndZOrder(_wpHwnd, pw, ph);
                    }
                    POINT pt;
                    if (GetCursorPos(out pt)) {
                        int pw = Math.Max(800, GetSystemMetrics(0));
                        int ph = Math.Max(600, GetSystemMetrics(1));
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
                        int vkL = swapped ? 0x02 : 0x01;
                        int vkR = swapped ? 0x01 : 0x02;
                        int btn = 0;
                        if ((GetAsyncKeyState(vkL) & 0x8000) != 0) btn |= 1;
                        if ((GetAsyncKeyState(vkR) & 0x8000) != 0) btn |= 2;
                        if ((GetAsyncKeyState(0x04) & 0x8000) != 0) btn |= 4;

                        double wh = 0.0;
                        bool clk = false;
                        lock (_hookLock) {
                            wh = _wheelAccum;
                            clk = _clickPending;
                            _wheelAccum = 0.0;
                            _clickPending = false;
                        }
                        double wheelOut = (onDesk && (btn & 4) != 0 && Math.Abs(wh) > 0.01) ? Math.Round(wh, 3) : 0.0;
                        int clickOut = (clk && onDesk) ? 1 : 0;

                        string json = string.Format(
                            System.Globalization.CultureInfo.InvariantCulture,
                            "{{\"type\":\"wp_ptr\",\"nx\":{0:F5},\"ny\":{1:F5},\"px\":{2},\"py\":{3},\"btn\":{4},\"desk\":{5},\"icon\":false,\"wheel\":{6:F3},\"click\":{7}}}",
                            nx, ny, pt.x, pt.y, btn, onDesk ? "true" : "false", wheelOut, clickOut
                        );
                        BroadcastWs(json);
                    }
                } catch { }
                Thread.Sleep(16);
            }
        });
        t.IsBackground = true;
        t.Start();
    }

    private static void SendWsFrame(Stream s, string text)
    {
        byte[] payload = Encoding.UTF8.GetBytes(text);
        List<byte> frame = new List<byte>();
        frame.Add(0x81);
        if (payload.Length < 126) {
            frame.Add((byte)payload.Length);
        } else if (payload.Length <= 65535) {
            frame.Add(126);
            frame.Add((byte)((payload.Length >> 8) & 0xFF));
            frame.Add((byte)(payload.Length & 0xFF));
        } else {
            frame.Add(127);
            long len = payload.Length;
            for (int i = 7; i >= 0; i--) frame.Add((byte)((len >> (8 * i)) & 0xFF));
        }
        frame.AddRange(payload);
        byte[] arr = frame.ToArray();
        s.Write(arr, 0, arr.Length);
        s.Flush();
    }

    private static void BroadcastWs(string text)
    {
        lock (_wsLock) {
            for (int i = _wsClients.Count - 1; i >= 0; i--) {
                try {
                    SendWsFrame(_wsClients[i], text);
                } catch {
                    try { _wsClients[i].Close(); } catch { }
                    _wsClients.RemoveAt(i);
                }
            }
        }
    }

    private static string ReadWsTextMessage(Stream s)
    {
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
            try { s.Write(new byte[] { 0x8A, 0x00 }, 0, 2); } catch { }
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
            BroadcastWs(jss.Serialize(msg));
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

        BroadcastWs(resJson);
        return resJson;
    }

    private static void WriteHttpResponse(Stream s, int code, string statusText, string contentType, byte[] bodyBytes)
    {
        if (bodyBytes == null) bodyBytes = new byte[0];
        StringBuilder hdr = new StringBuilder();
        hdr.AppendFormat("HTTP/1.1 {0} {1}\r\n", code, statusText);
        hdr.AppendFormat("Content-Type: {0}\r\n", contentType);
        hdr.AppendFormat("Content-Length: {0}\r\n", bodyBytes.Length);
        hdr.Append("Cache-Control: no-store, no-cache, must-revalidate\r\n");
        hdr.Append("Access-Control-Allow-Origin: *\r\n");
        hdr.Append("Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n");
        hdr.Append("Access-Control-Allow-Headers: Content-Type, X-Ophanim-Token\r\n");
        hdr.Append("Access-Control-Allow-Private-Network: true\r\n");
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

                if (headers.ContainsKey("Origin")) {
                    string orig = headers["Origin"].Trim().ToLowerInvariant();
                    if (orig.Length > 0 && orig != "null" && !orig.StartsWith("file://") &&
                        !orig.StartsWith("http://127.0.0.1") && !orig.StartsWith("http://localhost")) {
                        WriteHttpResponse(ns, 403, "Forbidden", "application/json", Encoding.UTF8.GetBytes("{\"ok\":false}"));
                        return;
                    }
                }

                if (method == "OPTIONS") {
                    WriteHttpResponse(ns, 204, "No Content", "text/plain", new byte[0]);
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

                    lock (_wsLock) { _wsClients.Add(ns); }
                    try {
                        SendWsFrame(ns, BuildStatusJson(true));
                        if (File.Exists(_configPath)) {
                            string savedRaw = File.ReadAllText(_configPath, Encoding.UTF8);
                            if (!string.IsNullOrEmpty(savedRaw)) {
                                SendWsFrame(ns, "{\"type\":\"ophanim_config_updated\",\"config\":" + savedRaw + "}");
                            }
                        }
                        JavaScriptSerializer jss = new JavaScriptSerializer();
                        jss.MaxJsonLength = 8 * 1024 * 1024;
                        while (true) {
                            string msg = ReadWsTextMessage(ns);
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
                                    BroadcastWs(jss.Serialize(upd));
                                } else if (t == "ophanim_preview_completion" || t == "ophanim_ack_completions") {
                                    BroadcastWs(msg);
                                } else if (t == "ophanim_wallpaper_hello") {
                                    SendWsFrame(ns, BuildStatusJson(true));
                                    if (File.Exists(_configPath)) {
                                        string sr = File.ReadAllText(_configPath, Encoding.UTF8);
                                        if (!string.IsNullOrEmpty(sr)) SendWsFrame(ns, "{\"type\":\"ophanim_config_updated\",\"config\":" + sr + "}");
                                    }
                                }
                            } catch { }
                        }
                    } finally {
                        lock (_wsLock) { _wsClients.Remove(ns); }
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
                        Encoding.UTF8.GetBytes("{\"ok\":true,\"service\":\"ophanim_toy_native\",\"interactiveWallpaper\":true}"));
                    return;
                }
                if (pathOnly == "/api/shutdown" && method == "POST") {
                    WriteHttpResponse(ns, 200, "OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes("{\"ok\":true}"));
                    ThreadPool.QueueUserWorkItem(delegate(object o) { Thread.Sleep(120); Environment.Exit(0); });
                    return;
                }
                if (pathOnly == "/api/wallpaper") {
                    string res = (method == "POST") ? HandleWallpaperRequestJson(bodyStr) : BuildStatusJson(true);
                    WriteHttpResponse(ns, 200, "OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes(res));
                    return;
                }
                if (pathOnly == "/api/save-config" && method == "POST") {
                    JavaScriptSerializer jss = new JavaScriptSerializer();
                    jss.MaxJsonLength = 8 * 1024 * 1024;
                    Dictionary<string, object> d = jss.Deserialize<Dictionary<string, object>>(bodyStr);
                    if (d != null && d.ContainsKey("config")) SaveConfigObject(d["config"]);
                    WriteHttpResponse(ns, 200, "OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes("{\"ok\":true}"));
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
                        WriteHttpResponse(ns, 200, "OK", "text/html; charset=utf-8", htmlBytes);
                        return;
                    }
                }
                WriteHttpResponse(ns, 404, "Not Found", "text/plain", Encoding.ASCII.GetBytes("Not Found"));
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

        TcpListener listener = new TcpListener(IPAddress.Loopback, port);
        try { listener.Server.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true); } catch { }
        listener.Start();

        StartMouseHookThread();
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
                    Process.Start(browserExe, string.Format(
                        "--user-data-dir=\"{0}\" --app=\"{1}\" --window-size=1560,940 --force-dark-mode --no-first-run --no-default-browser-check --disable-features=Translate,EdgeSidebar,msEdgeSidebarV2",
                        appProf, appUrl
                    ));
                } catch { }
            });
            winOpenThread.IsBackground = true;
            winOpenThread.Start();
        }

        Thread idleMonitor = new Thread(delegate() {
            int idleSec = 0;
            Thread.Sleep(30000);
            while (true) {
                Thread.Sleep(5000);
                int clientsNow;
                lock (_wsLock) { clientsNow = _wsClients.Count; }
                if (!_wpActive && clientsNow == 0) {
                    idleSec += 5;
                    if (idleSec >= 180) Environment.Exit(0);
                } else {
                    idleSec = 0;
                }
            }
        });
        idleMonitor.IsBackground = true;
        idleMonitor.Start();

        while (true) {
            TcpClient c = listener.AcceptTcpClient();
            ThreadPool.QueueUserWorkItem(delegate(object st) { HandleClient((TcpClient)st); }, c);
        }
    }
}
'@

# 2. Cache compiled C# assembly to `.ophanim_toy_cache\OphanimToyHost_<hash>.dll` for <150ms instant startup!
Add-Type -AssemblyName 'System.Web.Extensions'
Add-Type -AssemblyName 'System.Management'
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
        Add-Type -ReferencedAssemblies @('System.dll', 'System.Core.dll', 'System.Management.dll', 'System.Web.Extensions.dll') -TypeDefinition $CsSource -OutputAssembly $CachedDll -ErrorAction Stop
        Add-Type -Path $CachedDll -ErrorAction Stop
    } catch {
        Add-Type -ReferencedAssemblies @('System.dll', 'System.Core.dll', 'System.Management.dll', 'System.Web.Extensions.dll') -TypeDefinition $CsSource
    }
}

$BrowserExe = Find-ChromiumExe
[OphanimToyNativeHost]::StartServer($HtmlFile, $CacheDir, $BrowserExe, $Port, (-not $IsWakeOnly), $AppUrl)
