import subprocess
import sys
from pathlib import Path

base = Path.home() / 'AppData' / 'Local' / 'ms-playwright'
exes = list(base.glob('**/chrome.exe'))
if exes:
    chrome_exe = exes[0]
    user_dir = Path(__file__).resolve().parent / "backend" / "storage" / "browser_profile"
    user_dir.mkdir(parents=True, exist_ok=True)
    cmd = f'start "" "{chrome_exe}" --user-data-dir="{user_dir}" "https://www.linkedin.com/login"'
    print("Launching Chrome command:", cmd)
    subprocess.Popen(cmd, shell=True)
    print("Successfully launched!")
else:
    print("Chrome exe not found!")
