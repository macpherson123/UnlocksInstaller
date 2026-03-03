#!/usr/bin/env python3
"""
Paul Unlocks All-In-One Installer (single-file)

- Bootstraps required system & python packages (handles "externally-managed-environment")
- Creates a desktop entry for easy launcher access
- GUI with branding, icon, colors (approx from uploaded image)
- Selective install options with "None" choices
- Live disk & network usage and connectivity indicator
- Collapsible detailed log
- "Remove all components" button to undo installed items (best-effort)
- Saves settings to ~/.paul_unlocks_installer_config.json

Usage:
  1) Save as ~/paul_unlocks_installer.py
  2) chmod +x ~/paul_unlocks_installer.py
  3) python3 ~/paul_unlocks_installer.py

Before running: crop/save the padlock icon from your uploaded image to a PNG (e.g. ~/Pictures/padlock.png)
so you can choose it in the GUI. The script will also create a .desktop entry using the chosen icon.
"""
# --- BEGIN bootstrap: robust auto-bootstrap for externally-managed envs ---
import os, sys, shutil, subprocess, importlib
from pathlib import Path

_MARKER_ENV = "PAUL_UNLOCKS_REQ_DONE"
_VENV_DIR = Path.home() / ".local" / "share" / "paul_unlocks_installer_venv"

def run_cmd(cmd, capture=True):
    try:
        proc = subprocess.run(["bash","-lc", cmd], stdout=subprocess.PIPE if capture else None,
                              stderr=subprocess.STDOUT, universal_newlines=True)
        out = proc.stdout if capture else ""
        return proc.returncode, (out or "")
    except Exception as e:
        return 1, str(e)

def apt_available():
    return shutil.which("apt") is not None

def dpkg_installed(pkg):
    rc, _ = run_cmd(f"dpkg -s {pkg} >/dev/null 2>&1; echo $?", capture=True)
    return rc == 0

def try_import(name):
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False

def install_system_packages(pkgs, logger=print):
    if not apt_available():
        logger("apt not available: skipping system package auto-install.")
        return False
    missing = [p for p in pkgs if not dpkg_installed(p)]
    if not missing:
        logger("All system packages present.")
        return True
    logger("Missing system packages: " + ", ".join(missing))
    if os.geteuid() != 0:
        logger("Using sudo to install system packages (you may be prompted for your password).")
        rc, out = run_cmd("sudo apt update -y")
        if rc != 0:
            logger("apt update failed:\n" + out)
            return False
        rc, out = run_cmd("sudo apt install -y " + " ".join(missing))
    else:
        rc, out = run_cmd("apt update -y")
        if rc != 0:
            logger("apt update failed:\n" + out)
            return False
        rc, out = run_cmd("apt install -y " + " ".join(missing))
    if rc != 0:
        logger("apt install failed:\n" + out)
        return False
    logger("System packages installed/available.")
    return True

def ensure_pip_packages(pkgs, logger=print):
    python_cmd = sys.executable or "python3"
    externally_managed = False
    failed = []
    for pkg in pkgs:
        if try_import(pkg):
            logger(f"Python package '{pkg}' already installed.")
            continue
        logger(f"Attempting: {python_cmd} -m pip install --user {pkg}")
        rc, out = run_cmd(f'{python_cmd} -m pip install --user {pkg}', capture=True)
        if rc == 0 and try_import(pkg):
            logger(f"Installed '{pkg}' successfully.")
            continue
        text = (out or "").lower()
        if "externally-managed" in text or "externally managed" in text:
            logger(f"pip reported externally-managed-environment while installing '{pkg}'.")
            externally_managed = True
            failed.append(pkg)
            continue
        logger(f"pip install failed for {pkg} (rc={rc}). Output:\n{out}")
        failed.append(pkg)
    if externally_managed:
        return "externally_managed", failed
    if failed:
        return False, failed
    return True, []

def apt_install_equivalents(mapping, logger=print):
    if not apt_available():
        logger("apt not available; cannot install apt equivalents.")
        return list(mapping.keys())
    apt_pkgs = []
    for pip_name, apt_name in mapping.items():
        if try_import(pip_name):
            continue
        if apt_name:
            apt_pkgs.append(apt_name)
    if not apt_pkgs:
        logger("No apt equivalents needed.")
        return []
    logger("Attempting apt install of equivalents: " + ", ".join(apt_pkgs))
    if os.geteuid() != 0:
        rc, out = run_cmd("sudo apt update -y")
        if rc != 0:
            logger("apt update failed:\n" + out)
            return list(mapping.keys())
        rc, out = run_cmd("sudo apt install -y " + " ".join(apt_pkgs))
    else:
        rc, out = run_cmd("apt update -y")
        if rc != 0:
            logger("apt update failed:\n" + out)
            return list(mapping.keys())
        rc, out = run_cmd("apt install -y " + " ".join(apt_pkgs))
    if rc != 0:
        logger("apt install of equivalents failed:\n" + out)
        return list(mapping.keys())
    still_missing = [p for p in mapping.keys() if not try_import(p)]
    return still_missing

def create_and_use_venv(pkgs, logger=print):
    python_cmd = sys.executable or "python3"
    venv_dir = _VENV_DIR
    logger(f"Creating virtual environment at: {venv_dir}")
    if not (venv_dir / "bin" / "python").exists():
        rc, out = run_cmd(f'{python_cmd} -m venv "{venv_dir}"')
        if rc != 0:
            logger("Failed to create venv; attempting to install python3-venv via apt.")
            if apt_available():
                if os.geteuid() != 0:
                    rc2, out2 = run_cmd("sudo apt update -y && sudo apt install -y python3-venv")
                else:
                    rc2, out2 = run_cmd("apt update -y && apt install -y python3-venv")
                if rc2 == 0:
                    rc, out = run_cmd(f'{python_cmd} -m venv "{venv_dir}"')
            if rc != 0:
                logger("Failed to create virtualenv and cannot continue automatically.")
                return False
    venv_python = str(venv_dir / "bin" / "python")
    rc, out = run_cmd(f'"{venv_python}" -m pip install --upgrade pip setuptools wheel', capture=True)
    if rc != 0:
        logger("Failed to upgrade pip in venv:\n" + out)
        return False
    for pkg in pkgs:
        logger(f'Installing "{pkg}" into venv')
        rc, out = run_cmd(f'"{venv_python}" -m pip install {pkg}', capture=True)
        if rc != 0:
            logger(f'pip install inside venv failed for {pkg}:\n{out}')
            return False
        rc, out = run_cmd(f'"{venv_python}" -c "import {pkg}; print(1)"', capture=True)
        if rc != 0:
            logger(f"Import test for {pkg} failed inside venv:\n{out}")
            return False
    logger("Re-executing script with venv python so the venv packages are used...")
    os.environ[_MARKER_ENV] = "1"
    os.execv(venv_python, [venv_python] + sys.argv)

def ensure_requirements_with_external_handling(system_pkgs, pip_pkgs, apt_equivs=None, logger=print):
    logger("Ensuring system packages (if apt available)...")
    if apt_available():
        install_system_packages(system_pkgs, logger=logger)
    else:
        logger("apt not available; please ensure system packages are installed manually if required.")
    logger("Ensuring pip packages (attempting user installs)...")
    result = ensure_pip_packages(pip_pkgs, logger=logger)
    if isinstance(result, tuple):
        ok, failed = result
        if ok == "externally_managed":
            logger("Detected externally-managed environment (PEP 668). Trying apt equivalents or a per-user venv.")
            if apt_equivs:
                missing_after_apt = apt_install_equivalents({p: apt_equivs.get(p,"") for p in failed}, logger=logger)
                if not missing_after_apt:
                    logger("Requirements satisfied via apt equivalents.")
                    return True
                else:
                    logger("Some remain missing; creating venv for the missing pkgs.")
                    create_and_use_venv(missing_after_apt, logger=logger)
                    return True
            else:
                create_and_use_venv(failed, logger=logger)
                return True
        elif ok is True:
            logger("pip packages installed successfully.")
            return True
        else:
            logger("pip install had errors for: " + ", ".join(failed))
            if apt_equivs:
                missing_after_apt = apt_install_equivalents({p: apt_equivs.get(p,"") for p in failed}, logger=logger)
                if not missing_after_apt:
                    return True
                create_and_use_venv(missing_after_apt, logger=logger)
                return True
            else:
                create_and_use_venv(failed, logger=logger)
                return True
    else:
        if result:
            return True
        else:
            logger("Unknown error while installing pip packages.")
            return False

if os.environ.get(_MARKER_ENV) != "1":
    def _log(msg):
        sys.stdout.write(msg if msg.endswith("\n") else msg + "\n")
        sys.stdout.flush()
    SYSTEM_PKGS = ["python3-tk", "python3-pip", "curl", "wget", "unzip", "git", "ca-certificates", "gnupg"]
    PIP_PKGS = ["psutil"]
    APT_EQUIVS = {"psutil":"python3-psutil"}
    ok = ensure_requirements_with_external_handling(SYSTEM_PKGS, PIP_PKGS, apt_equivs=APT_EQUIVS, logger=_log)
    if not ok:
        _log("Bootstrap failed. Please install required packages and re-run.")
        _log("System packages: " + ", ".join(SYSTEM_PKGS))
        _log("Python packages: " + ", ".join(PIP_PKGS))
        sys.exit(1)
    os.environ[_MARKER_ENV] = "1"
# --- END bootstrap ---

# Now proceed to import GUI libs and psutil
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, filedialog, messagebox
except Exception as e:
    print("Tkinter not importable after bootstrap. Please restart your Linux VM or re-run the script.")
    raise

import psutil
import json
import threading
import time
from datetime import datetime

# ---------- App constants & paths ----------
CONFIG_PATH = Path.home() / ".paul_unlocks_installer_config.json"
LOG_DIR = Path.home() / ".paul_unlocks_installer_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
SCRIPT_PATH = Path(__file__).expanduser().resolve()
APP_VERSION = "1.1.0"

# --- Professional Dark Theme ---
BG_DARK      = "#111318"   # main background
BG_CARD      = "#1a1d24"   # card / panel background
BG_CARD_ALT  = "#1f2229"   # slightly lighter card
BG_INPUT     = "#252830"   # input field background
BG_HOVER     = "#2a2d36"   # hover state
BORDER       = "#2e3140"   # subtle borders
BORDER_FOCUS = "#3b82f6"   # focused element accent (blue)
ACCENT       = "#3b82f6"   # primary accent (blue)
ACCENT_HOVER = "#2563eb"   # accent hover
ACCENT_GREEN = "#22c55e"   # success / green
ACCENT_GOLD  = "#f59e0b"   # gold / warning
BAD          = "#ef4444"   # error / red
TEXT_PRIMARY  = "#f1f5f9"  # primary text
TEXT_SECONDARY= "#94a3b8"  # secondary / muted text
TEXT_DIM      = "#64748b"  # dimmed text

BRAND_NAME = "Paul Unlocks"
BRAND_URL  = "https://www.paulunlocks.net"

# Unicode glyphs for status indicators
ICON_LOCK   = "\U0001F513"  # unlocked padlock
ICON_CHECK  = "\u2713"
ICON_CROSS  = "\u2717"
ICON_GEAR   = "\u2699"
ICON_DISK   = "\u25C9"
ICON_NET    = "\u25C8"
ICON_BOLT   = "\u26A1"

# ---------- Helpers ----------
def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.load(open(CONFIG_PATH))
        except Exception:
            return {}
    return {}

# Desktop entry creation
def create_desktop_entry(script_path, icon_path=None):
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    name = "paul-unlocks-installer"
    desktop_file = desktop_dir / f"{name}.desktop"
    exec_path = f"{sys.executable} {script_path}"
    icon_field = icon_path if icon_path else ""
    content = f"""[Desktop Entry]
Name={BRAND_NAME} Installer
Comment=Setup Node, Bun, Expo, EAS, VS Code, Android Studio, emulator
Exec={exec_path}
Icon={icon_field}
Terminal=false
Type=Application
Categories=Development;IDE;
"""
    try:
        desktop_file.write_text(content)
        # make it readable/executable
        desktop_file.chmod(0o644)
        return desktop_file
    except Exception as e:
        print("Failed to create desktop entry:", e)
        return None

# ---------- Monitoring ----------
class SystemMonitor(threading.Thread):
    def __init__(self, interval=1.0, disk_cb=None, net_cb=None, stop_event=None):
        super().__init__(daemon=True)
        self.interval = interval
        self.disk_cb = disk_cb
        self.net_cb = net_cb
        self._stop = stop_event or threading.Event()
        self._last_disk = psutil.disk_io_counters()
        self._last_net = psutil.net_io_counters()

    def run(self):
        while not self._stop.is_set():
            try:
                du = psutil.disk_usage("/")
                dio = psutil.disk_io_counters()
                rps = max(0, dio.read_bytes - self._last_disk.read_bytes)/self.interval
                wps = max(0, dio.write_bytes - self._last_disk.write_bytes)/self.interval
                self._last_disk = dio
                if self.disk_cb:
                    self.disk_cb({"percent": du.percent, "read": rps, "write": wps})
            except Exception:
                pass
            try:
                ni = psutil.net_io_counters()
                rx = max(0, ni.bytes_recv - self._last_net.bytes_recv)/self.interval
                tx = max(0, ni.bytes_sent - self._last_net.bytes_sent)/self.interval
                self._last_net = ni
                if self.net_cb:
                    self.net_cb({"rx": rx, "tx": tx})
            except Exception:
                pass
            time.sleep(self.interval)

# ---------- Interactive runner (prompts on failure) ----------
class InteractiveRunner:
    def __init__(self, log_func, decision_func):
        self.log = log_func
        self.decision = decision_func

    def run(self, cmd, env=None):
        self.log(f"\n$ {cmd}\n")
        proc = subprocess.Popen(["bash","-lc",cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=env)
        for line in proc.stdout:
            self.log(line)
        proc.wait()
        self.log(f"[exit {proc.returncode}]\n")
        if proc.returncode != 0:
            choice = self.decision({"cmd":cmd, "rc":proc.returncode})
            if choice == "retry":
                return self.run(cmd, env=env)
            elif choice == "continue":
                return proc.returncode
            elif choice == "continue_offline":
                return proc.returncode
            else:
                raise RuntimeError("Aborted by user during command: " + cmd)
        return proc.returncode

# ---------- Main GUI ----------
class PaulUnlocksInstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{BRAND_NAME} Installer  v{APP_VERSION}")
        self.geometry("960x640")
        self.minsize(820, 540)
        self.configure(bg=BG_DARK)
        self.cfg = load_config()
        self.icon_path = self.cfg.get("icon_path", "")
        self.create_desktop_on_start = self.cfg.get("create_desktop_on_start", True)
        self._log_visible = False
        self._setup_styles()
        self._build_ui()

        self.monitor_stop = threading.Event()
        self.monitor = SystemMonitor(interval=1.0, disk_cb=self._disk_cb, net_cb=self._net_cb, stop_event=self.monitor_stop)
        self.monitor.start()
        self.runner = InteractiveRunner(self._append_log, self._on_cmd_fail)

        if self.create_desktop_on_start:
            de = create_desktop_entry(str(SCRIPT_PATH), self.icon_path)
            if de:
                self._append_log(f"  Desktop entry created: {de}\n")
            self.create_desktop_on_start = False
            self.cfg["create_desktop_on_start"] = False
            save_config(self.cfg)

    # ── Styles ──────────────────────────────────────────────
    def _setup_styles(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass

        # Frame / background
        s.configure("TFrame", background=BG_DARK)
        s.configure("Card.TFrame", background=BG_CARD)

        # Labels
        s.configure("TLabel", background=BG_DARK, foreground=TEXT_PRIMARY,
                     font=("Helvetica", 10))
        s.configure("Card.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY,
                     font=("Helvetica", 10))
        s.configure("CardDim.TLabel", background=BG_CARD, foreground=TEXT_SECONDARY,
                     font=("Helvetica", 9))
        s.configure("Header.TLabel", background=BG_DARK, foreground=TEXT_PRIMARY,
                     font=("Helvetica", 18, "bold"))
        s.configure("SubHeader.TLabel", background=BG_DARK, foreground=TEXT_SECONDARY,
                     font=("Helvetica", 10))
        s.configure("Version.TLabel", background=BG_DARK, foreground=TEXT_DIM,
                     font=("Helvetica", 9))
        s.configure("MonKey.TLabel", background=BG_CARD, foreground=TEXT_SECONDARY,
                     font=("Helvetica", 9))
        s.configure("MonVal.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY,
                     font=("Helvetica Neue", 10, "bold"))
        s.configure("StatusOk.TLabel", background=BG_CARD, foreground=ACCENT_GREEN,
                     font=("Helvetica", 10, "bold"))
        s.configure("StatusBad.TLabel", background=BG_CARD, foreground=BAD,
                     font=("Helvetica", 10, "bold"))
        s.configure("StepLabel.TLabel", background=BG_CARD, foreground=TEXT_SECONDARY,
                     font=("Helvetica", 9))

        # LabelFrames (cards)
        s.configure("TLabelframe", background=BG_CARD, foreground=TEXT_SECONDARY,
                     borderwidth=1, relief="solid",
                     font=("Helvetica", 9, "bold"))
        s.configure("TLabelframe.Label", background=BG_CARD, foreground=TEXT_SECONDARY,
                     font=("Helvetica", 9, "bold"))

        # Buttons
        s.configure("TButton", background=BG_CARD_ALT, foreground=TEXT_PRIMARY,
                     borderwidth=0, padding=(14, 7),
                     font=("Helvetica", 10))
        s.map("TButton",
               background=[("active", BG_HOVER), ("pressed", BORDER)],
               foreground=[("active", TEXT_PRIMARY)])

        s.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                     borderwidth=0, padding=(16, 8),
                     font=("Helvetica", 10, "bold"))
        s.map("Accent.TButton",
               background=[("active", ACCENT_HOVER), ("pressed", "#1d4ed8")])

        s.configure("Danger.TButton", background="#7f1d1d", foreground="#fca5a5",
                     borderwidth=0, padding=(14, 7),
                     font=("Helvetica", 9))
        s.map("Danger.TButton",
               background=[("active", "#991b1b")],
               foreground=[("active", "#fecaca")])

        # Combobox
        s.configure("TCombobox", fieldbackground=BG_INPUT, background=BG_INPUT,
                     foreground=TEXT_PRIMARY, selectbackground=ACCENT,
                     selectforeground="#ffffff", borderwidth=1,
                     padding=4, arrowsize=14)
        s.map("TCombobox",
               fieldbackground=[("readonly", BG_INPUT)],
               foreground=[("readonly", TEXT_PRIMARY)])
        self.option_add("*TCombobox*Listbox.background", BG_INPUT)
        self.option_add("*TCombobox*Listbox.foreground", TEXT_PRIMARY)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

        # Entry
        s.configure("TEntry", fieldbackground=BG_INPUT, foreground=TEXT_PRIMARY,
                     insertcolor=TEXT_PRIMARY, borderwidth=1, padding=4)

        # Progressbar
        s.configure("Custom.Horizontal.TProgressbar",
                     troughcolor=BG_INPUT, background=ACCENT,
                     borderwidth=0, thickness=10)

        # Separator
        s.configure("TSeparator", background=BORDER)

    # ── Build UI ────────────────────────────────────────────
    def _build_ui(self):
        # ── Top header bar ──
        hdr = tk.Frame(self, bg=BG_DARK)
        hdr.pack(fill="x", padx=20, pady=(16, 0))

        brand_frame = tk.Frame(hdr, bg=BG_DARK)
        brand_frame.pack(side="left")
        tk.Label(brand_frame, text=f"{ICON_LOCK}  {BRAND_NAME}", bg=BG_DARK,
                 fg=TEXT_PRIMARY, font=("Helvetica", 20, "bold")).pack(side="left")
        tk.Label(brand_frame, text=f"  v{APP_VERSION}", bg=BG_DARK,
                 fg=TEXT_DIM, font=("Helvetica", 10)).pack(side="left", pady=(6, 0))

        right_hdr = tk.Frame(hdr, bg=BG_DARK)
        right_hdr.pack(side="right")
        ttk.Button(right_hdr, text=f"{ICON_GEAR}  Choose Icon",
                   command=self._choose_icon).pack(side="right")

        # tagline
        tk.Label(self, text="Professional Development Environment Installer",
                 bg=BG_DARK, fg=TEXT_SECONDARY,
                 font=("Helvetica", 10)).pack(anchor="w", padx=22, pady=(2, 0))

        # separator
        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x", padx=20, pady=(12, 0))

        # ── Main content (PanedWindow for resizable columns) ──
        content = tk.Frame(self, bg=BG_DARK)
        content.pack(fill="both", expand=True, padx=20, pady=(12, 0))
        content.columnconfigure(0, weight=0, minsize=310)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        # ── LEFT: scrollable options column ──
        left_outer = tk.Frame(content, bg=BG_DARK)
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_outer.rowconfigure(0, weight=1)
        left_outer.columnconfigure(0, weight=1)

        left_canvas = tk.Canvas(left_outer, bg=BG_DARK, highlightthickness=0, width=290)
        left_scroll = ttk.Scrollbar(left_outer, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll.grid(row=0, column=1, sticky="ns")

        left = tk.Frame(left_canvas, bg=BG_DARK)
        left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))

        def _on_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        left_canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Windows/Mac
        left_canvas.bind_all("<Button-4>", lambda e: left_canvas.yview_scroll(-1, "units"))
        left_canvas.bind_all("<Button-5>", lambda e: left_canvas.yview_scroll(1, "units"))

        def _card(parent, title, icon=""):
            lf = ttk.LabelFrame(parent, text=f"  {icon}  {title}")
            lf.pack(fill="x", pady=(0, 8), padx=(0, 4))
            return lf

        # Node
        lf_node = _card(left, "Node.js Runtime", "\u2B22")
        self.node_choice = tk.StringVar(value=self.cfg.get("node", "lts"))
        ttk.Label(lf_node, text="Node version (nvm):", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 2))
        ttk.Combobox(lf_node, textvariable=self.node_choice,
                      values=["none", "lts", "22", "20", "18"], width=12,
                      state="readonly").grid(row=0, column=1, padx=8, pady=(6, 2))
        self.bun_choice = tk.StringVar(
            value="install" if self.cfg.get("install_bun", False) else "none")
        ttk.Label(lf_node, text="Bun runtime:", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=8, pady=(2, 8))
        ttk.Combobox(lf_node, textvariable=self.bun_choice,
                      values=["none", "install"], width=12,
                      state="readonly").grid(row=1, column=1, padx=8, pady=(2, 8))

        # Expo / EAS
        lf_expo = _card(left, "Expo / EAS CLI", "\u25B6")
        self.expo_choice = tk.StringVar(
            value="install" if self.cfg.get("install_expo", True) else "none")
        self.eas_choice = tk.StringVar(
            value="install" if self.cfg.get("install_eas", True) else "none")
        ttk.Label(lf_expo, text="Expo CLI:", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 2))
        ttk.Combobox(lf_expo, textvariable=self.expo_choice,
                      values=["none", "install"], width=12,
                      state="readonly").grid(row=0, column=1, padx=8, pady=(6, 2))
        ttk.Label(lf_expo, text="EAS CLI:", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=8, pady=(2, 8))
        ttk.Combobox(lf_expo, textvariable=self.eas_choice,
                      values=["none", "install"], width=12,
                      state="readonly").grid(row=1, column=1, padx=8, pady=(2, 8))

        # Editor
        lf_editor = _card(left, "Editor / IDE", "\u270E")
        self.editor_choice = tk.StringVar(value=self.cfg.get("editor", "vscode"))
        ttk.Label(lf_editor, text="Editor:", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 2))
        ttk.Combobox(lf_editor, textvariable=self.editor_choice,
                      values=["none", "vscode", "code-server", "android-studio"],
                      width=16, state="readonly").grid(row=0, column=1, padx=8, pady=(6, 2))
        self.android_studio_url = tk.StringVar(
            value=self.cfg.get("android_studio_url", ""))
        ttk.Label(lf_editor, text="Studio URL:", style="CardDim.TLabel").grid(
            row=1, column=0, sticky="w", padx=8, pady=(2, 2))
        ttk.Entry(lf_editor, textvariable=self.android_studio_url, width=28).grid(
            row=1, column=1, padx=8, pady=(2, 8), sticky="ew")

        # Java
        lf_java = _card(left, "Java Development Kit", "\u2615")
        self.java_choice = tk.StringVar(
            value=self.cfg.get("java_choice", "openjdk-17"))
        ttk.Combobox(lf_java, textvariable=self.java_choice,
                      values=["none", "openjdk-11", "openjdk-17", "openjdk-20",
                               "system-or-bundled"],
                      width=20, state="readonly").pack(padx=8, pady=8, fill="x")

        # Emulator
        lf_emu = _card(left, "Android Emulator", "\u25B7")
        self.local_emu = tk.StringVar(
            value="none" if not self.cfg.get("local_emulator", False) else "install")
        ttk.Label(lf_emu, text="Emulator:", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=8, pady=(6, 2))
        ttk.Combobox(lf_emu, textvariable=self.local_emu,
                      values=["none", "install"], width=12,
                      state="readonly").grid(row=0, column=1, padx=8, pady=(6, 2))
        self.emu_api = tk.StringVar(value=self.cfg.get("emulator_api", "33"))
        ttk.Label(lf_emu, text="API level:", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=8, pady=(2, 8))
        ttk.Combobox(lf_emu, textvariable=self.emu_api,
                      values=["none", "34", "33", "32", "31", "30"],
                      width=12, state="readonly").grid(row=1, column=1, padx=8, pady=(2, 8))

        # Reset button
        ttk.Button(left, text=f"{ICON_CROSS}  Remove All Components",
                   style="Danger.TButton",
                   command=self._confirm_remove_all).pack(
            fill="x", pady=(4, 12), padx=(0, 4))

        # ── RIGHT: actions, monitor, progress ──
        right = tk.Frame(content, bg=BG_DARK)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(3, weight=1)

        # Action buttons bar
        actions = tk.Frame(right, bg=BG_DARK)
        actions.pack(fill="x", pady=(0, 10))

        self.start_btn = ttk.Button(actions, text=f"{ICON_BOLT}  Start Install",
                                     style="Accent.TButton",
                                     command=self._start_install)
        self.start_btn.pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Save Settings",
                   command=self._save_settings).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Open Logs",
                   command=lambda: os.system(f'xdg-open "{LOG_DIR}" || true')).pack(
            side="left", padx=(0, 6))
        self._log_toggle_btn = ttk.Button(actions, text="Show Log",
                                            command=self._toggle_log)
        self._log_toggle_btn.pack(side="left", padx=(0, 6))

        # Progress card
        prog_card = tk.Frame(right, bg=BG_CARD, padx=16, pady=12)
        prog_card.pack(fill="x", pady=(0, 10))
        tk.Label(prog_card, text="PROGRESS", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Helvetica", 8, "bold"), anchor="w").pack(fill="x")
        self.progress = ttk.Progressbar(prog_card, orient="horizontal",
                                         mode="determinate",
                                         style="Custom.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(6, 4))
        self.step_var = tk.StringVar(value="Ready")
        tk.Label(prog_card, textvariable=self.step_var, bg=BG_CARD,
                 fg=TEXT_SECONDARY, font=("Helvetica", 9), anchor="w").pack(fill="x")

        # System monitor card
        mon_card = tk.Frame(right, bg=BG_CARD, padx=16, pady=12)
        mon_card.pack(fill="x", pady=(0, 10))
        tk.Label(mon_card, text="SYSTEM MONITOR", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Helvetica", 8, "bold"), anchor="w").pack(fill="x", pady=(0, 8))

        mon_grid = tk.Frame(mon_card, bg=BG_CARD)
        mon_grid.pack(fill="x")
        mon_grid.columnconfigure(1, weight=1)
        mon_grid.columnconfigure(3, weight=1)

        def _mon_row(parent, row, col_offset, key_text, var_style="MonVal.TLabel"):
            ttk.Label(parent, text=key_text, style="MonKey.TLabel").grid(
                row=row, column=col_offset, sticky="w", padx=(0, 6), pady=2)
            v = tk.StringVar(value="-")
            ttk.Label(parent, textvariable=v, style=var_style).grid(
                row=row, column=col_offset + 1, sticky="w", pady=2)
            return v

        self.disk_var    = _mon_row(mon_grid, 0, 0, f"{ICON_DISK} Disk:")
        self.net_var     = _mon_row(mon_grid, 0, 2, f"{ICON_NET} Net:")
        self.disk_io_var = _mon_row(mon_grid, 1, 0, "   IO:")
        self.net_status  = _mon_row(mon_grid, 1, 2, "   Status:")
        self.net_lbl = None  # we'll track the label for color changes

        # Re-create net status with direct tk.Label for color control
        for child in mon_grid.grid_slaves(row=1, column=3):
            child.destroy()
        self.net_status = tk.StringVar(value="Checking...")
        self.net_lbl = tk.Label(mon_grid, textvariable=self.net_status,
                                 bg=BG_CARD, fg=TEXT_DIM,
                                 font=("Helvetica Neue", 10, "bold"))
        self.net_lbl.grid(row=1, column=3, sticky="w", pady=2)

        # Log panel (initially hidden)
        self.log_frame = tk.Frame(right, bg=BG_CARD)
        self.log_widget = scrolledtext.ScrolledText(
            self.log_frame, height=12, state="disabled", wrap="word",
            bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY,
            selectbackground=ACCENT, selectforeground="#ffffff",
            font=("Consolas", 9), borderwidth=0, padx=8, pady=8)
        self.log_widget.pack(fill="both", expand=True, padx=2, pady=2)
        self.log_frame.pack_forget()

        # ── Status bar at very bottom ──
        status_bar = tk.Frame(self, bg=BG_CARD, height=28)
        status_bar.pack(fill="x", side="bottom")
        tk.Label(status_bar, text=f"  {BRAND_NAME}  |  {BRAND_URL}  |  v{APP_VERSION}",
                 bg=BG_CARD, fg=TEXT_DIM, font=("Helvetica", 8),
                 anchor="w").pack(side="left", padx=8, pady=4)

        # start net check
        self._stop_net_check = threading.Event()
        threading.Thread(target=self._net_connectivity_loop, daemon=True).start()

    # ── Utilities ───────────────────────────────────────────
    def _choose_icon(self):
        p = filedialog.askopenfilename(
            title="Choose logo / icon (PNG recommended)",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.ico"), ("All", "*.*")])
        if p:
            self.icon_path = p
            self.cfg["icon_path"] = p
            save_config(self.cfg)
            create_desktop_entry(str(SCRIPT_PATH), p)
            self._append_log(f"  Icon set & desktop entry updated: {p}\n")

    def _toggle_log(self):
        if self._log_visible:
            self.log_frame.pack_forget()
            self._log_toggle_btn.configure(text="Show Log")
            self._log_visible = False
        else:
            self.log_frame.pack(fill="both", expand=True, pady=(0, 4))
            self._log_toggle_btn.configure(text="Hide Log")
            self._log_visible = True

    def _append_log(self, text):
        try:
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", text)
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")
        except Exception:
            pass

    def _disk_cb(self, info):
        self.disk_var.set(f"{info['percent']:.1f}%")
        self.disk_io_var.set(
            f"{self._format_bytes(info['read'])}/s R  |  "
            f"{self._format_bytes(info['write'])}/s W")

    def _net_cb(self, info):
        self.net_var.set(
            f"{self._format_bytes(info['rx'])} / {self._format_bytes(info['tx'])}")

    @staticmethod
    def _format_bytes(b):
        b = float(b)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(b) < 1024.0:
                return f"{b:3.1f} {unit}"
            b /= 1024.0
        return f"{b:.1f} PB"

    def _net_connectivity_loop(self):
        while not self._stop_net_check.is_set():
            rc, _ = run_cmd("ping -c 1 -W 1 8.8.8.8 >/dev/null 2>&1; echo $?",
                            capture=True)
            if rc == 0:
                self.net_status.set(f"{ICON_CHECK} Online")
                try:
                    self.net_lbl.configure(fg=ACCENT_GREEN)
                except Exception:
                    pass
            else:
                self.net_status.set(f"{ICON_CROSS} Offline")
                try:
                    self.net_lbl.configure(fg=BAD)
                except Exception:
                    pass
            time.sleep(3)

    # ── Command failure dialog ──────────────────────────────
    def _on_cmd_fail(self, info):
        cmd = info.get("cmd", "")[:200]
        rc = info.get("rc", 1)
        dlg = tk.Toplevel(self)
        dlg.title("Command Failed")
        dlg.configure(bg=BG_CARD)
        dlg.geometry("520x200")
        dlg.grab_set()

        tk.Label(dlg, text=f"Command exited with code {rc}",
                 bg=BG_CARD, fg=BAD, font=("Helvetica", 11, "bold")).pack(
            padx=16, pady=(16, 4))
        tk.Label(dlg, text=cmd, bg=BG_CARD, fg=TEXT_SECONDARY,
                 font=("Consolas", 9), wraplength=480, justify="left").pack(
            padx=16, pady=(0, 12))

        res = {"choice": None}

        def ch(c):
            res["choice"] = c
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg=BG_CARD)
        btn_frame.pack(pady=(0, 16))

        for text, val, style in [
            ("Retry", "retry", "Accent.TButton"),
            ("Skip", "continue", "TButton"),
            ("Continue Offline", "continue_offline", "TButton"),
            ("Abort", "abort", "Danger.TButton"),
        ]:
            ttk.Button(btn_frame, text=text, style=style,
                       command=lambda v=val: ch(v)).pack(side="left", padx=4)

        dlg.wait_window()
        return res["choice"] or "abort"

    def _save_settings(self):
        self.cfg.update({
            "node": self.node_choice.get(),
            "install_bun": (self.bun_choice.get() == "install"),
            "install_expo": (self.expo_choice.get() == "install"),
            "install_eas": (self.eas_choice.get() == "install"),
            "editor": self.editor_choice.get(),
            "android_studio_url": self.android_studio_url.get(),
            "java_choice": self.java_choice.get(),
            "local_emulator": (self.local_emu.get() == "install"),
            "emulator_api": self.emu_api.get(),
            "icon_path": getattr(self, "icon_path", ""),
        })
        save_config(self.cfg)
        self._append_log(f"  {ICON_CHECK} Settings saved.\n")

    def _start_install(self):
        self.start_btn.configure(state="disabled")
        steps = []
        steps.append(("System Prerequisites", self._step_prereqs))
        if self.java_choice.get() != "none":
            steps.append(("Java JDK", self._step_java))
        if self.node_choice.get() != "none":
            steps.append(("Node.js (nvm)", self._step_nvm))
        if self.bun_choice.get() == "install":
            steps.append(("Bun Runtime", self._step_bun))
        if self.expo_choice.get() == "install" or self.eas_choice.get() == "install":
            steps.append(("Expo / EAS CLI", self._step_expo_eas))
        if self.editor_choice.get() != "none":
            if self.editor_choice.get() == "vscode":
                steps.append(("VS Code", self._step_vscode))
            elif self.editor_choice.get() == "code-server":
                steps.append(("code-server", self._step_code_server))
            elif self.editor_choice.get() == "android-studio":
                steps.append(("Android Studio", self._step_android_studio))
        if self.local_emu.get() == "install":
            steps.append(("KVM / QEMU", self._step_kvm))
            steps.append(("Android SDK + Emulator", self._step_emulator))
        steps.append(("ADB (platform-tools)", self._step_adb))
        # show log automatically
        if not self._log_visible:
            self._toggle_log()
        threading.Thread(target=self._run_steps, args=(steps,), daemon=True).start()

    def _run_steps(self, steps):
        total = len(steps)
        self.progress["maximum"] = total
        for i, (label, fn) in enumerate(steps, start=1):
            self.progress["value"] = i - 1
            self.step_var.set(f"[{i}/{total}]  {label}")
            self._append_log(f"\n{'='*50}\n  {ICON_BOLT} {label}\n{'='*50}\n")
            try:
                fn(self.runner)
            except Exception as e:
                self._append_log(f"  {ICON_CROSS} Exception in {label}: {e}\n")
            self.progress["value"] = i
        self.step_var.set(f"{ICON_CHECK}  Installation complete")
        self.start_btn.configure(state="normal")
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        logf = LOG_DIR / f"paul_unlocks_install_{ts}.log"
        try:
            with open(logf, "w") as f:
                f.write(self.log_widget.get("1.0", "end"))
            self._append_log(f"\n  {ICON_CHECK} Log saved to {logf}\n")
        except Exception:
            pass
        messagebox.showinfo(BRAND_NAME,
                            f"Installation finished.\nLog saved to:\n{logf}")

    # ---- step implementations (use runner.run) ----
    def _step_prereqs(self, runner):
        cmds = [
            "sudo apt update -y",
            "sudo apt upgrade -y",
            "sudo apt install -y curl wget git build-essential ca-certificates gnupg apt-transport-https unzip"
        ]
        for c in cmds:
            runner.run(c)
        return 0

    def _step_java(self, runner):
        choice = self.java_choice.get()
        if choice == "system-or-bundled":
            runner.log("Using Android Studio bundled JRE where applicable; skipping system JDK.\n")
            return 0
        if choice == "none":
            return 0
        pkg = {"openjdk-11":"openjdk-11-jdk","openjdk-17":"openjdk-17-jdk","openjdk-20":"openjdk-20-jdk"}.get(choice,"openjdk-11-jdk")
        return runner.run(f"sudo apt update -y && sudo apt install -y {pkg}")

    def _step_nvm(self, runner):
        v = self.node_choice.get()
        runner.run('curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh | bash')
        nvm_init = 'export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" || true'
        if v == "lts":
            return runner.run(f'{nvm_init} && nvm install --lts && nvm alias default node')
        else:
            return runner.run(f'{nvm_init} && nvm install {v} && nvm alias default {v}')

    def _step_bun(self, runner):
        return runner.run('curl -fsSL https://bun.sh/install | bash')

    def _step_expo_eas(self, runner):
        nvm_init = 'export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" || true'
        return runner.run(f'{nvm_init} && npm install -g expo-cli eas-cli')

    def _step_vscode(self, runner):
        steps = [
            'wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg',
            'sudo install -o root -g root -m 644 packages.microsoft.gpg /usr/share/keyrings/',
            'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | sudo tee /etc/apt/sources.list.d/vscode.list',
            'sudo apt update -y',
            'sudo apt install -y code'
        ]
        for c in steps:
            runner.run(c)
        return 0

    def _step_code_server(self, runner):
        return runner.run('curl -fsSL https://code-server.dev/install.sh | sh')

    def _step_android_studio(self, runner):
        url = self.android_studio_url.get().strip()
        if not url:
            runner.log("No Android Studio URL provided; skipping automated download.\n")
            return 0
        cmd = f'mkdir -p "$HOME/Downloads" && wget -O "$HOME/Downloads/android-studio.tar.gz" "{url}" || true && tar -xzf "$HOME/Downloads/android-studio.tar.gz" -C "$HOME/Downloads" || true && sudo rm -rf /opt/android-studio || true && sudo mv "$HOME/Downloads/android-studio" /opt/android-studio || true && sudo ln -sf /opt/android-studio/bin/studio.sh /usr/local/bin/android-studio || true'
        return runner.run(cmd)

    def _step_kvm(self, runner):
        rs = ['sudo apt update -y', 'sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils', 'sudo adduser $USER kvm || true', 'sudo adduser $USER libvirt || true', 'newgrp kvm || true', 'ls -l /dev/kvm || true']
        for c in rs:
            runner.run(c)
        return 0

    def _step_emulator(self, runner):
        api = self.emu_api.get()
        if api == "none":
            runner.log("Skipped emulator install by user selection.\n"); return 0
        sdk_root = Path.home() / "Android" / "Sdk"
        runner.run(f'mkdir -p "{sdk_root}"')
        zip_target = Path.home() / "Downloads" / "commandlinetools-linux.zip"
        runner.run(f'wget -O "{zip_target}" "https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip" || true')
        runner.run(f'unzip -o "{zip_target}" -d "{sdk_root}/cmdline-tools-temp" || true')
        runner.run(f'mkdir -p "{sdk_root}/cmdline-tools/latest"')
        runner.run(f'mv "{sdk_root}/cmdline-tools-temp/cmdline-tools/"* "{sdk_root}/cmdline-tools/latest/" || true')
        runner.run(f'rm -rf "{sdk_root}/cmdline-tools-temp" || true')
        env_line = f'export ANDROID_SDK_ROOT="{sdk_root}"'
        path_line = f'export PATH="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/platform-tools:$PATH"'
        packages = f'"platform-tools" "emulator" "platforms;android-{api}" "system-images;android-{api};google_apis;x86_64"'
        runner.run(f'{env_line} && {path_line} && yes | sdkmanager --sdk_root="{sdk_root}" {packages}')
        runner.run(f'{env_line} && {path_line} && echo no | avdmanager create avd -n paul_unlocks_avd -k "system-images;android-{api};google_apis;x86_64" --device "pixel" --force || true')
        return 0

    def _step_adb(self, runner):
        return runner.run('sudo apt update -y && sudo apt install -y android-tools-adb')

    # ── Remove all ────────────────────────────────────────────
    def _confirm_remove_all(self):
        if not messagebox.askyesno(
                BRAND_NAME,
                "This will attempt to remove all components installed by "
                "this tool.\n\nAre you sure you want to continue?"):
            return
        if not self._log_visible:
            self._toggle_log()
        threading.Thread(target=self._remove_all, daemon=True).start()

    def _remove_all(self):
        self._append_log(f"\n{'='*50}\n  {ICON_CROSS} Removing installed components\n{'='*50}\n")
        nvm_init = ('export NVM_DIR="$HOME/.nvm" && '
                    '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" || true')
        cmds = [
            f'{nvm_init} && npm uninstall -g expo-cli eas-cli || true',
            'sudo apt remove --purge -y code || true',
            'sudo apt remove --purge -y android-studio || true',
            'sudo apt autoremove -y || true',
            'rm -rf $HOME/.bun || true',
            'rm -rf $HOME/Android || true',
            'rm -rf $HOME/.cache/bun || true',
            'rm -rf /opt/android-studio || true',
            'rm -rf $HOME/.nvm || true',
            'rm -rf $HOME/.local/share/code-server || true',
        ]
        for c in cmds:
            try:
                self._append_log(f"  $ {c}\n")
                run_cmd(c, capture=False)
            except Exception as e:
                self._append_log(f"  {ICON_CROSS} Error: {e}\n")
        self._append_log(f"\n  {ICON_CHECK} Removal complete. Check log for details.\n")
        messagebox.showinfo(BRAND_NAME,
                            "Removal attempts finished.\nCheck the log for details.")

# ---------- Launch ----------
def main():
    app = PaulUnlocksInstallerApp()
    icon = app.cfg.get("icon_path", "")
    if icon and Path(icon).exists():
        try:
            img = tk.PhotoImage(file=icon)
            app.iconphoto(False, img)
        except Exception:
            pass
    app.mainloop()

if __name__ == "__main__":
    main()
