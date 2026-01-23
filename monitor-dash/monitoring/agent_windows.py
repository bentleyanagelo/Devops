# monitoring/agent_windows.py
import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import time
import requests
import psutil
import json
from datetime import datetime

class ComputerMonitorAgent(win32serviceutil.ServiceFramework):
    _svc_name_ = "DowntimeMonitorAgent"
    _svc_display_name_ = "Computer Downtime Monitor Agent"
    _svc_description_ = "Monitors computer status and reports to central server"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.server_url = "http://your-server:5000"
        self.computer_id = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        self.main()

    def get_system_info(self):
        """Get system information"""
        return {
            'hostname': socket.gethostname(),
            'ip_address': socket.gethostbyname(socket.gethostname()),
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat()
        }

    def send_heartbeat(self):
        """Send heartbeat to server"""
        try:
            data = self.get_system_info()
            response = requests.post(
                f"{self.server_url}/api/heartbeat",
                json=data,
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error sending heartbeat: {e}")
        return None

    def main(self):
        """Main agent loop"""
        while True:
            self.send_heartbeat()
            time.sleep(60)  # Send every minute

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(ComputerMonitorAgent)