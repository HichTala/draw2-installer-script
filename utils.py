import os
import sys
import zipfile
import requests
import subprocess

IS_WINDOWS = sys.platform.startswith("win")


def set_python_path(new_path):
    key_path = r"Software\HichTala\Draw2"
    # Create or open the key with write access
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
    winreg.SetValueEx(key, "python_path", 0, winreg.REG_SZ, new_path)
    winreg.CloseKey(key)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def download_file(url, dest_path, progress_callback=None, chunk_size=8192):
    # streaming download with optional progress callback(bytes_received, total_size)
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        received = 0
        ensure_dir(os.path.dirname(dest_path))
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                received += len(chunk)
                if progress_callback:
                    progress_callback(received, total)
    return dest_path


def extract_zip(zip_path, dest_dir):
    ensure_dir(dest_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            # Compute the destination path
            extracted_path = os.path.join(dest_dir, member.filename)

            # Handle directories
            if member.is_dir():
                ensure_dir(extracted_path)
                continue

            # Skip if file already exists
            if os.path.exists(extracted_path):
                continue

            # Ensure the parent directory exists
            ensure_dir(os.path.dirname(extracted_path))

            # Extract the file manually
            with zf.open(member) as source, open(extracted_path, "wb") as target:
                target.write(source.read())


def run_subprocess(args, env=None, cwd=None, stdout=None, stderr=None, timeout=None):
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    proc = subprocess.Popen(args, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                            cwd=cwd)
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


def run_python_pip(python_exe, get_pip, requirements_txt, target):
    # ensure pip exists, then run pip install -r requirements.txt --target <site-packages-or-lib-dir>
    subprocess_return = []
    # try ensurepip
    subprocess_return.append(run_subprocess([python_exe, get_pip]))
    # upgrade pip
    subprocess_return.append(run_subprocess([python_exe, "-m", "pip", "install", "--upgrade", "pip"]))
    # install torch
    subprocess_return.append(run_subprocess([python_exe, "-m", "pip", "install", "torch", "torchvision", "--index-url",
                                             "https://download.pytorch.org/whl/cu126"]))
    # install requirements
    subprocess_return.append(run_subprocess([python_exe, "-m", "pip", "install", "-r", requirements_txt]))
    # install draw
    subprocess_return.append(
        run_subprocess([python_exe, "-m", "pip", "install",
                        "https://github.com/HichTala/draw2-obsplugin/releases/download/0.1.0/draw-0.0.1-py3-none-any.whl",
                        "--target", target]))
    return subprocess_return


if IS_WINDOWS:
    import winreg


    def find_obs_installs_from_registry():
        installs = []
        # check both HKLM 64/32-bit uninstall locations
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
                key = winreg.OpenKey(hive, uninstall)
            except FileNotFoundError:
                continue

            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                try:
                    subkey = winreg.OpenKey(key, sub)
                    try:
                        name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        install_loc = None
                        try:
                            install_loc = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                        except FileNotFoundError:
                            # fall back to parsing 'UninstallString'
                            try:
                                us = winreg.QueryValueEx(subkey, "UninstallString")[0]
                                # sometimes UninstallString contains path to uninstaller under install dir
                                # keep it for heuristic
                                install_loc = os.path.dirname(us)
                            except FileNotFoundError:
                                install_loc = ""
                        if name and "obs" in name.lower():
                            installs.append({
                                "name": name,
                                "path": install_loc or ""
                            })
                    except FileNotFoundError:
                        pass
                except OSError:
                    pass
                i += 1
        # deduplicate by path
        seen = set()
        unique = []
        for it in installs:
            p = os.path.normpath(it["path"]) if it["path"] else ""
            if p and p not in seen:
                unique.append(it)
                seen.add(p)
        return unique


    def find_obs_installs():
        results = []
        results.extend(find_obs_installs_from_registry())
        # also add common paths
        candidates = [
            r"C:\Program Files\obs-studio",
            r"C:\Program Files (x86)\obs-studio",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "obs-studio"),
            r"C:\Program Files\OBS Studio"
        ]
        for c in candidates:
            if os.path.isdir(c):
                results.append({"name": "OBS Studio (detected)", "path": c})
        # dedupe (simple)
        seen = set()
        out = []
        for r in results:
            p = os.path.normpath(r["path"]) if r["path"] else ""
            if p and p not in seen:
                seen.add(p)
                out.append(r)
        return out

else:
    def find_obs_installs():
        # Non-windows: look at common linux/osx locations or return empty
        possible = [
            "/usr/share/obs/obs-plugins",
            "/usr/lib/obs-plugins",
            "/Applications/OBS.app/Contents/Plugins"
        ]
        results = []
        for p in possible:
            if os.path.isdir(p):
                results.append({"name": "OBS (detected)", "path": p})
        return results
