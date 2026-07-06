"""Small framed-protocol diagnostic for a connected VuNMix device."""

import argparse
import pathlib
import sys
import time

import serial


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "desktop"))
from protocol import Command, FrameParser, encode_frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", default="COM14", help="USB CDC port, e.g. COM3")
    args = parser.parse_args()

    try:
        connection = serial.Serial(args.port, 115200, timeout=0.1)
    except (serial.SerialException, OSError) as exc:
        raise SystemExit(f"Failed to open {args.port}: {exc}")

    frame_parser = FrameParser()
    print(f"Opened {args.port}; requesting firmware version")
    connection.write(encode_frame(Command.TEST))
    connection.flush()

    try:
        while True:
            data = connection.read(max(1, min(connection.in_waiting, 256)))
            for command, payload in frame_parser.feed(data):
                if command == Command.TEST:
                    print("Firmware:", payload.decode("ascii", errors="replace"))
                else:
                    print(f"{command.name}: {payload.hex(' ')}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        connection.close()


if __name__ == "__main__":
    main()
