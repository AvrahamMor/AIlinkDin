import os
import subprocess
import json

try:
    output = subprocess.check_output(
        'powershell -Command "Get-CimInstance Win32_Process -Filter \\"name = \'chrome.exe\'\\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"',
        shell=True
    ).decode('utf-8', errors='ignore').strip()

    if output:
        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]
        killed = 0
        for p in data:
            cmd = p.get("CommandLine") or ""
            pid = p.get("ProcessId")
            if "ms-playwright" in cmd or "browser_profile" in cmd:
                print(f"Killing ghost Chromium process {pid}")
                os.system(f"taskkill /F /PID {pid} >nul 2>&1")
                killed += 1
        print(f"Total killed: {killed}")
    else:
        print("No ghost chrome processes found.")
except Exception as e:
    print("Clean ghost check completed.")
