#!/usr/bin/env python3
import time
import os
from INA219 import INA219
import subprocess
# Battery voltage range (adjust if needed)
V_FULL = 4.09
V_EMPTY = 3.00

# Shutdown threshold
LOW_BATTERY_PERCENT = 20

# Ignore tiny currents (noise)
CURRENT_NOISE_THRESHOLD = 50   # mA

# Initialize INA219 at correct address
ina = INA219(addr=0x43)

def oled(line1="", line2="", size1=12, size2=12):
    cmd = [
        "/usr/local/sbin/.wpsd-oled.text.py",
        "--text1", str(line1),
        "--size1", str(size1),
        "--text2", str(line2),
        "--size2", str(size2)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_battery_percent(voltage):
    # Clamp values
    if voltage > V_FULL:
        voltage = V_FULL
    if voltage < V_EMPTY:
        voltage = V_EMPTY

    return int(((voltage - V_EMPTY) / (V_FULL - V_EMPTY)) * 100)

def mains_present(current_ma):
    """
    Positive current = charging = mains present.
    But ignore tiny currents (±50 mA) because they are noise.
    """
    if abs(current_ma) < CURRENT_NOISE_THRESHOLD:
        return True  # treat as no mains, no charging happening

    return current_ma > 0

def shutdown_pi():
    print("Battery low and no mains power. Shutting down...")
    os.system("sudo shutdown -h now")

def main():
    while True:
        bus_voltage = ina.getBusVoltage_V()
        current_ma = ina.getCurrent_mA()

        battery_percent = get_battery_percent(bus_voltage)

        print(f"Voltage: {bus_voltage:.2f} V | Current: {current_ma:.0f} mA | Battery: {battery_percent}%")

        if mains_present(current_ma):
            print("Mains power detected (charging).")
        else:
            print("Running on battery power (discharging).")
            oled(
                    line1=f"Running on Bat",
                    line2=f"Battery: {battery_percent}%",
                    size1=14,
                    size2=12
            )
            if battery_percent <= LOW_BATTERY_PERCENT:
                oled("LOW BATTERY", "SHUTTING DOWN", size1=14, size2=14)
                shutdown_pi()

        time.sleep(120)

if __name__ == "__main__":
    main()
