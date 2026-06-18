import subprocess
import re

def kill_zombies():
    print("Finding Chrome processes...")
    try:
        output = subprocess.check_output('C:\\Windows\\System32\\wbem\\wmic.exe process where "name=\'chrome.exe\'" get processid,commandline', shell=True).decode('utf-8', errors='ignore')
    except Exception as e:
        print("Error getting processes:", e)
        return

    lines = output.split('\n')
    killed = 0
    for line in lines:
        if '--headless' in line.lower() or 'puppeteer' in line.lower() or 'account-' in line.lower():
            # Find PID which is at the end of the line
            parts = line.strip().split()
            if parts:
                pid = parts[-1]
                if pid.isdigit():
                    print(f"Killing PID {pid}...")
                    try:
                        subprocess.call(f'C:\\Windows\\System32\\taskkill.exe /F /PID {pid} /T', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        killed += 1
                    except Exception as e:
                        print(f"Failed to kill {pid}: {e}")
    
    print(f"Done. Successfully killed {killed} headless Chrome instances.")

if __name__ == '__main__':
    kill_zombies()
