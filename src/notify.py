"""TurboPlay — notificação Windows toast (stdlib only, via PowerShell)."""
from __future__ import annotations

import subprocess

_PS_TEMPLATE = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{0}</text><text>{1}</text></binding></visual></toast>')
$toast = New-Object Windows.UI.Notifications.ToastNotification($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("TurboPlay").Show($toast)
"""


def notify(title: str, message: str) -> bool:
    try:
        script = _PS_TEMPLATE.format(
            title.replace("'", "''"), message.replace("'", "''"))
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            capture_output=True, timeout=20,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
