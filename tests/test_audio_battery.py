import unittest
from types import SimpleNamespace
from unittest.mock import patch

from skills.audio_manager import (
    _battery_from_bluetoothctl,
    _battery_from_bluez_dbus,
    bluetooth_battery,
)


class BluetoothBatteryTests(unittest.TestCase):
    @patch("skills.audio_manager._run")
    def test_bluetoothctl_hex_percentage(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=(
                "Device 24:B2:31:81:7B:05\n"
                "    Connected: yes\n"
                "    Battery Percentage: 0x57 (87)\n"
            ),
            stderr="",
        )

        self.assertEqual(
            _battery_from_bluetoothctl(),
            87,
        )

    @patch("skills.audio_manager._run")
    def test_bluez_battery1_percentage(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout="y 73\n",
            stderr="",
        )

        self.assertEqual(
            _battery_from_bluez_dbus(),
            73,
        )

    @patch(
        "skills.audio_manager._battery_from_bluez_dbus",
        return_value=None,
    )
    @patch(
        "skills.audio_manager._battery_from_bluetoothctl",
        return_value=None,
    )
    @patch(
        "skills.audio_manager.bluetooth_connected",
        return_value=True,
    )
    def test_connected_but_battery_unavailable(
        self,
        connected,
        bluetoothctl,
        dbus,
    ):
        data = bluetooth_battery()

        self.assertTrue(
            data["connected"]
        )
        self.assertFalse(
            data["available"]
        )
        self.assertIsNone(
            data["percentage"]
        )

    @patch(
        "skills.audio_manager.bluetooth_connected",
        return_value=False,
    )
    def test_disconnected(
        self,
        connected,
    ):
        data = bluetooth_battery()

        self.assertFalse(
            data["connected"]
        )
        self.assertFalse(
            data["available"]
        )
        self.assertIsNone(
            data["percentage"]
        )


if __name__ == "__main__":
    unittest.main()
