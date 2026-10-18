import traceback
from multiprocessing.connection import Connection

import pynmea2
import serial
from serial.serialutil import EIGHTBITS, PARITY_NONE, STOPBITS_ONE

from bicycleinit.BicycleSensor import BicycleSensor
from sensor_config import GPSConfigurator


svs = []
pdop = None
hdop = None
vdop = None

def parse_gps_stats(sentence):
  global svs, pdop, hdop, vdop
  try:
    msg = pynmea2.parse(sentence)

    # GSA contains satellites used and DOP values
    if msg.sentence_type == 'GSA':
      svs = []
      for i in range(1, 13):
        attr = f'sv_id{i:02d}'
        val = getattr(msg, attr, None)
        if val and str(val).strip():
          svs.append(str(val).strip())

      pdop = getattr(msg, 'pdop', None)
      hdop = getattr(msg, 'hdop', None)
      vdop = getattr(msg, 'vdop', None)
      return svs, pdop, hdop, vdop
  except pynmea2.nmea.ParseError:
      pass
  return None

def parse_nmea_sentence(sentence):
  try:
    msg = pynmea2.parse(sentence)
    # Only process GLL sentences
    if msg.sentence_type == 'GLL' and msg.status == 'A':
      return msg.latitude, msg.longitude
  except pynmea2.nmea.ParseError:
      pass
  return None

def main(bicycleinit: Connection, name: str, args: dict):
  global svs, pdop, hdop, vdop

  sensor = BicycleSensor(bicycleinit, name, args)

  port = args.get('port', '/dev/ttyACM0')
  configurator = GPSConfigurator(port_device=port)
  port = configurator.port

  try:
    sensor.send_msg(f'Opening serial port {configurator.port} for {configurator.device_name}')
    ser = serial.Serial(configurator.port, baudrate=9600, parity=PARITY_NONE, bytesize=EIGHTBITS, stopbits=STOPBITS_ONE, timeout=5.0)
  except serial.SerialException as e:
    sensor.send_msg(f'Error opening serial port {port}: {e}')
    return

  sensor.write_header(['latitude', 'longitude', 'sv_used', 'hdop', 'pdop', 'vdop'])

  try:
    while True:
      line = ser.readline().decode('ascii', errors='ignore').strip()

      parse_gps_stats(line)
      gps_stats = ['|'.join(svs), hdop, pdop, vdop]

      gps_data = parse_nmea_sentence(line)

      if gps_data is not None:
        sensor.write_measurement(list(gps_data) + gps_stats)

  except KeyboardInterrupt:
    pass
  except Exception as e:
    sensor.send_msg({'type': 'log', 'level': 'error', 'msg': str(e)})
    sensor.send_msg({'type': 'log', 'level': 'error', 'msg': traceback.format_exc()})
  finally:
    ser.close()
    sensor.shutdown()

if __name__ == "__main__":
  main(None, "bicyclegps", {'port': '/dev/ttyACM0'})
