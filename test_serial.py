import serial
import time
import struct

# Open COM14 at 115200 baud
try:
    ser = serial.Serial('COM14', 115200, timeout=1)
    print("Opened COM14")
except Exception as e:
    print(f"Failed to open COM14: {e}")
    exit(1)

# Send TEST command
print("Sending TEST command (1)...")
ser.write(bytes([1]))
ser.flush()

time.sleep(0.1)
response = ser.read(ser.in_waiting)
print(f"Response: {response}")

# Send OK command
print("Sending OK command (2)...")
ser.write(bytes([2]))
ser.flush()

# Listen for incoming data
print("Listening for incoming data... (Turn the knob or press buttons)")
try:
    while True:
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            print(f"Received: {[hex(x) for x in data]}")
        time.sleep(0.01)
except KeyboardInterrupt:
    print("Closing...")
    ser.close()
