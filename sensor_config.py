from __future__ import annotations
import serial
import serial.tools.list_ports
from dataclasses import dataclass
import time


@dataclass
class GPSDeviceConfig:
    usb_vendor_id: int | None
    usb_product_id: int
    baudrate: int
    bootstrap_cmds: list[bytes]


class GPSConfigurator:
    SUPPORTED_DEVICES: dict[str, GPSDeviceConfig] = {
        "u-blox-7": GPSDeviceConfig(
            usb_vendor_id=0x1546,  # u-blox AG
            usb_product_id=0x01A7,
            baudrate=9600,
            bootstrap_cmds=[
                # 1. Disable GGA
                b"\xb5\x62\x06\x01\x08\x00\xf0\x00\x00\x00\x00\x00\x00\x00\xff\x23",
                # 2. Disable RMC
                b"\xb5\x62\x06\x01\x08\x00\xf0\x04\x00\x00\x00\x00\x00\x00\x03\x3f",
                # 3. Disable GSV
                b"\xb5\x62\x06\x01\x08\x00\xf0\x03\x00\x00\x00\x00\x00\x00\x02\x38",
                # 4. Disable VTG
                b"\xb5\x62\x06\x01\x08\x00\xf0\x05\x00\x00\x00\x00\x00\x00\x04\x46",
                # 5. Enable GLL
                b"\xb5\x62\x06\x01\x08\x00\xf0\x01\x01\x01\x01\x01\x01\x00\x05\x3e",
                # 6. Enable GSA
                b"\xb5\x62\x06\x01\x08\x00\xf0\x02\x01\x01\x01\x01\x01\x00\x06\x45",
            ],
        ),
        "adafruit-ultimate-gps": GPSDeviceConfig(
            usb_vendor_id=0x10C4,  # Silicon Labs
            usb_product_id=0xEA60,
            baudrate=9600,
            bootstrap_cmds=[
                b"$PMTK314,1,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0*28\r\n"
            ],
        ),
    }

    def __init__(self, *, port_device: str | None = None):
        self.device_name, self.port = self._detect_gps_device(target_port=port_device)

        if not self.device_name or not self.port:
            target_info = f" on port '{port_device}'" if port_device else ""
            raise ValueError(f"No valid GPS device found{target_info}.")

    @property
    def config(self) -> GPSDeviceConfig | None:
        if self.device_name:
            return self.SUPPORTED_DEVICES.get(self.device_name)
        return None

    def _detect_gps_device(
        self, *, target_port: str | None = None
    ) -> tuple[str | None, str | None]:
        com_ports = serial.tools.list_ports.comports()
        detected: dict[str, tuple[str, str]] = {}

        for port in com_ports:
            for dev_name, config in self.SUPPORTED_DEVICES.items():
                pid_match = port.pid == config.usb_product_id
                vid_match = (
                    config.usb_vendor_id is None or port.vid == config.usb_vendor_id
                )
                if pid_match and vid_match:
                    detected[port.device] = (dev_name, port.device)
                    break

        if not detected:
            return None, None

        # Return target_port if present; fall back to the first detected device otherwise
        if target_port and target_port in detected:
            return detected[target_port]

        return next(iter(detected.values()))

    def configure_gps(self, *, gps_serial: serial.Serial) -> bool:
        config = self.config
        if not config:
            return False

        for cmd in config.bootstrap_cmds:
            gps_serial.write(cmd)
            gps_serial.flush()
            time.sleep(0.01)

        time.sleep(0.5)
        gps_serial.reset_input_buffer()
        return True


def main():
    try:
        for port in serial.tools.list_ports.comports():
            vid_str = f"0x{port.vid:04X}" if port.vid else "None"
            pid_str = f"0x{port.pid:04X}" if port.pid else "None"
            print(f"Port: {port.device} | VID: {vid_str} | PID: {pid_str} | Desc: {port.description}")

        configurator = GPSConfigurator()
        dev_config = configurator.config
        baudrate = dev_config.baudrate if dev_config else 9600

        print(
            f"Detected GPS: {configurator.device_name} on {configurator.port} @ {baudrate} baud"
        )

        with serial.Serial(
            port=configurator.port,
            baudrate=baudrate,
            timeout=2.0,
        ) as gps_serial:
            if configurator.configure_gps(gps_serial=gps_serial):
                print("Bootstrap commands sent successfully.")

            # Read loop
            for _ in range(1000):
                line = gps_serial.read_until(b"\r\n")
                if not line:
                    continue  # Timeout hit with no data

                sentence = line.decode("ascii", errors="replace").strip()
                if sentence:
                    print("GPS:", sentence)

    except (ValueError, serial.SerialException) as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("\nExiting program.")


if __name__ == "__main__":
    main()