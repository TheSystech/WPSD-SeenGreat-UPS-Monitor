#!/usr/bin/env python3
# =============================================================================
# UPS_combined.py
#
# Combined UPS battery monitor script.
# Merges: INA219.py, wpsd-oled.text.py, and UPS.py into a single file.
#
# - INA219 driver communicates with the INA219 current/voltage sensor via I2C.
# - OLED display functions render status text on an attached SSD1306 or SH1106.
# - UPS main loop monitors battery voltage/current, displays status on the
#   OLED, and triggers a safe shutdown when battery is critically low.
#
# =============================================================================
# UPS CONFIG FILE
# =============================================================================
# This script reads battery settings from an INI-style config file.
# Default path: /etc/ups_monitor.conf
#
# If the file does not exist or a value is missing/invalid, built-in defaults
# are used. Create the file with any or all of the following settings:
#
#   [Battery]
#   V_FULL = 4.09
#   V_EMPTY = 3.00
#   LOW_BATTERY_PERCENT = 20
#   CURRENT_NOISE_THRESHOLD = 50
#
# V_FULL                  - Voltage (V) considered 100% charge  (default: 4.09)
# V_EMPTY                 - Voltage (V) considered 0% charge    (default: 3.00)
# LOW_BATTERY_PERCENT     - Battery % that triggers shutdown     (default: 20)
# CURRENT_NOISE_THRESHOLD - Current (mA) below which readings   (default: 50)
#                           are treated as noise
# =============================================================================

# =============================================================================
# IMPORTS
# =============================================================================
import sys
import os
import time
import smbus
import configparser

try:
    from PIL import Image, ImageDraw, ImageFont
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306, sh1106
except ImportError as e:
    print(f"Error: Failed to import required libraries.", file=sys.stderr)
    print(f"Ensure 'Pillow' and 'luma.oled' are installed.", file=sys.stderr)
    print(f"Specific error: {e}", file=sys.stderr)
    sys.exit(1)


# =============================================================================
# CONFIG FILE PATHS
# =============================================================================
UPS_CONFIG_PATH = "/etc/ups_monitor.conf"
OLED_CONFIG_PATH = "/etc/mmdvmhost"
DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Built-in default values (used when config file is missing or incomplete)
DEFAULT_V_FULL = 4.09
DEFAULT_V_EMPTY = 3.00
DEFAULT_LOW_BATTERY_PERCENT = 20
DEFAULT_CURRENT_NOISE_THRESHOLD = 50   # mA


# =============================================================================
# UPS CONFIG LOADER
# =============================================================================

def load_ups_config(config_path=UPS_CONFIG_PATH):
    """Load battery settings from an INI config file.

    Returns a dict with keys:
        v_full, v_empty, low_battery_percent, current_noise_threshold

    Falls back to built-in defaults for any missing or invalid values.
    """
    settings = {
        "v_full": DEFAULT_V_FULL,
        "v_empty": DEFAULT_V_EMPTY,
        "low_battery_percent": DEFAULT_LOW_BATTERY_PERCENT,
        "current_noise_threshold": DEFAULT_CURRENT_NOISE_THRESHOLD,
    }

    if not os.path.exists(config_path):
        print(f"Info: UPS config file not found at {config_path}. Using all defaults.", file=sys.stderr)
        return settings

    config = configparser.ConfigParser()
    try:
        config.read(config_path)
    except Exception as e:
        print(f"Warning: Could not parse UPS config file {config_path}: {e}. Using all defaults.", file=sys.stderr)
        return settings

    if not config.has_section("Battery"):
        print(f"Warning: [Battery] section not found in {config_path}. Using all defaults.", file=sys.stderr)
        return settings

    # --- V_FULL ---
    if config.has_option("Battery", "V_FULL"):
        try:
            val = config.getfloat("Battery", "V_FULL")
            settings["v_full"] = val
            print(f"Config: V_FULL = {val}", file=sys.stderr)
        except ValueError:
            print(f"Warning: Invalid V_FULL in config. Using default: {DEFAULT_V_FULL}", file=sys.stderr)
    else:
        print(f"Info: V_FULL not set in config. Using default: {DEFAULT_V_FULL}", file=sys.stderr)

    # --- V_EMPTY ---
    if config.has_option("Battery", "V_EMPTY"):
        try:
            val = config.getfloat("Battery", "V_EMPTY")
            settings["v_empty"] = val
            print(f"Config: V_EMPTY = {val}", file=sys.stderr)
        except ValueError:
            print(f"Warning: Invalid V_EMPTY in config. Using default: {DEFAULT_V_EMPTY}", file=sys.stderr)
    else:
        print(f"Info: V_EMPTY not set in config. Using default: {DEFAULT_V_EMPTY}", file=sys.stderr)

    # --- LOW_BATTERY_PERCENT ---
    if config.has_option("Battery", "LOW_BATTERY_PERCENT"):
        try:
            val = config.getint("Battery", "LOW_BATTERY_PERCENT")
            settings["low_battery_percent"] = val
            print(f"Config: LOW_BATTERY_PERCENT = {val}", file=sys.stderr)
        except ValueError:
            print(f"Warning: Invalid LOW_BATTERY_PERCENT in config. Using default: {DEFAULT_LOW_BATTERY_PERCENT}", file=sys.stderr)
    else:
        print(f"Info: LOW_BATTERY_PERCENT not set in config. Using default: {DEFAULT_LOW_BATTERY_PERCENT}", file=sys.stderr)

    # --- CURRENT_NOISE_THRESHOLD ---
    if config.has_option("Battery", "CURRENT_NOISE_THRESHOLD"):
        try:
            val = config.getint("Battery", "CURRENT_NOISE_THRESHOLD")
            settings["current_noise_threshold"] = val
            print(f"Config: CURRENT_NOISE_THRESHOLD = {val}", file=sys.stderr)
        except ValueError:
            print(f"Warning: Invalid CURRENT_NOISE_THRESHOLD in config. Using default: {DEFAULT_CURRENT_NOISE_THRESHOLD}", file=sys.stderr)
    else:
        print(f"Info: CURRENT_NOISE_THRESHOLD not set in config. Using default: {DEFAULT_CURRENT_NOISE_THRESHOLD}", file=sys.stderr)

    # Sanity check: V_FULL must be greater than V_EMPTY
    if settings["v_full"] <= settings["v_empty"]:
        print(f"Warning: V_FULL ({settings['v_full']}) must be greater than V_EMPTY ({settings['v_empty']}). Reverting to defaults.", file=sys.stderr)
        settings["v_full"] = DEFAULT_V_FULL
        settings["v_empty"] = DEFAULT_V_EMPTY

    return settings


# =============================================================================
# INA219 DRIVER (from INA219.py)
# =============================================================================

# INA219 Register Addresses
_REG_CONFIG                 = 0x00
_REG_SHUNTVOLTAGE           = 0x01
_REG_BUSVOLTAGE             = 0x02
_REG_POWER                  = 0x03
_REG_CURRENT                = 0x04
_REG_CALIBRATION            = 0x05

class BusVoltageRange:
    """Constants for ``bus_voltage_range``"""
    RANGE_16V               = 0x00      # set bus voltage range to 16V
    RANGE_32V               = 0x01      # set bus voltage range to 32V (default)

class Gain:
    """Constants for ``gain``"""
    DIV_1_40MV              = 0x00      # shunt prog. gain set to  1, 40 mV range
    DIV_2_80MV              = 0x01      # shunt prog. gain set to /2, 80 mV range
    DIV_4_160MV             = 0x02      # shunt prog. gain set to /4, 160 mV range
    DIV_8_320MV             = 0x03      # shunt prog. gain set to /8, 320 mV range

class ADCResolution:
    """Constants for ``bus_adc_resolution`` or ``shunt_adc_resolution``"""
    ADCRES_9BIT_1S          = 0x00      #  9bit,   1 sample,     84us
    ADCRES_10BIT_1S         = 0x01      # 10bit,   1 sample,    148us
    ADCRES_11BIT_1S         = 0x02      # 11 bit,  1 sample,    276us
    ADCRES_12BIT_1S         = 0x03      # 12 bit,  1 sample,    532us
    ADCRES_12BIT_2S         = 0x09      # 12 bit,  2 samples,  1.06ms
    ADCRES_12BIT_4S         = 0x0A      # 12 bit,  4 samples,  2.13ms
    ADCRES_12BIT_8S         = 0x0B      # 12bit,   8 samples,  4.26ms
    ADCRES_12BIT_16S        = 0x0C      # 12bit,  16 samples,  8.51ms
    ADCRES_12BIT_32S        = 0x0D      # 12bit,  32 samples, 17.02ms
    ADCRES_12BIT_64S        = 0x0E      # 12bit,  64 samples, 34.05ms
    ADCRES_12BIT_128S       = 0x0F      # 12bit, 128 samples, 68.10ms

class Mode:
    """Constants for ``mode``"""
    POWERDOW                = 0x00      # power down
    SVOLT_TRIGGERED         = 0x01      # shunt voltage triggered
    BVOLT_TRIGGERED         = 0x02      # bus voltage triggered
    SANDBVOLT_TRIGGERED     = 0x03      # shunt and bus voltage triggered
    ADCOFF                  = 0x04      # ADC off
    SVOLT_CONTINUOUS        = 0x05      # shunt voltage continuous
    BVOLT_CONTINUOUS        = 0x06      # bus voltage continuous
    SANDBVOLT_CONTINUOUS    = 0x07      # shunt and bus voltage continuous


class INA219:
    def __init__(self, i2c_bus=1, addr=0x40):
        self.bus = smbus.SMBus(i2c_bus)
        self.addr = addr

        # Set chip to known config values to start
        self._cal_value = 0
        self._current_lsb = 0
        self._power_lsb = 0
        self.set_calibration_16V_5A()

    def read(self, address):
        data = self.bus.read_i2c_block_data(self.addr, address, 2)
        return ((data[0] * 256) + data[1])

    def write(self, address, data):
        temp = [0, 0]
        temp[1] = data & 0xFF
        temp[0] = (data & 0xFF00) >> 8
        self.bus.write_i2c_block_data(self.addr, address, temp)

    def set_calibration_16V_5A(self):
        """Configures to INA219 to be able to measure up to 16V and 5A of current. Counter
           overflow occurs at 16A.
           ..note :: These calculations assume a 0.01 shunt ohm resistor is present
        """
        # VBUS_MAX = 16V             (Assumes 16V, can also be set to 32V)
        # VSHUNT_MAX = 0.08          (Assumes Gain 2, 80mV, can also be 0.32, 0.16, 0.04)
        # RSHUNT = 0.01               (Resistor value in ohms)

        # 1. Determine max possible current
        # MaxPossible_I = VSHUNT_MAX / RSHUNT
        # MaxPossible_I = 8.0A

        # 2. Determine max expected current
        # MaxExpected_I = 5.0A

        # 3. Calculate possible range of LSBs (Min = 15-bit, Max = 12-bit)
        # MinimumLSB = MaxExpected_I/32767
        # MinimumLSB = 0.0001529              (61uA per bit)
        # MaximumLSB = MaxExpected_I/4096
        # MaximumLSB = 0,0012207              (488uA per bit)

        # 4. Choose an LSB between the min and max values
        #    (Preferrably a roundish number close to MinLSB)
        # CurrentLSB = 0.00016 (uA per bit)
        self._current_lsb = 0.1524  # Current LSB = 100uA per bit

        # 5. Compute the calibration register
        # Cal = trunc (0.04096 / (Current_LSB * RSHUNT))
        # Cal = 13434 (0x347a)
        self._cal_value = 26868

        # 6. Calculate the power LSB
        # PowerLSB = 20 * CurrentLSB
        # PowerLSB = 0.002 (2mW per bit)
        self._power_lsb = 0.003048  # Power LSB = 2mW per bit

        # 7. Compute the maximum current and shunt voltage values before overflow
        #
        # Max_Current = Current_LSB * 32767
        # Max_Current = 3.2767A before overflow
        #
        # If Max_Current > Max_Possible_I then
        #    Max_Current_Before_Overflow = MaxPossible_I
        # Else
        #    Max_Current_Before_Overflow = Max_Current
        # End If
        #
        # Max_ShuntVoltage = Max_Current_Before_Overflow * RSHUNT
        # Max_ShuntVoltage = 0.32V
        #
        # If Max_ShuntVoltage >= VSHUNT_MAX
        #    Max_ShuntVoltage_Before_Overflow = VSHUNT_MAX
        # Else
        #    Max_ShuntVoltage_Before_Overflow = Max_ShuntVoltage
        # End If

        # 8. Compute the Maximum Power
        # MaximumPower = Max_Current_Before_Overflow * VBUS_MAX
        # MaximumPower = 3.2 * 32V
        # MaximumPower = 102.4W

        # Set Calibration register to 'Cal' calculated above
        self.write(_REG_CALIBRATION, self._cal_value)

        # Set Config register to take into account the settings above
        self.bus_voltage_range = BusVoltageRange.RANGE_16V
        self.gain = Gain.DIV_2_80MV
        self.bus_adc_resolution = ADCResolution.ADCRES_12BIT_32S
        self.shunt_adc_resolution = ADCResolution.ADCRES_12BIT_32S
        self.mode = Mode.SANDBVOLT_CONTINUOUS
        self.config = self.bus_voltage_range << 13 | \
                      self.gain << 11 | \
                      self.bus_adc_resolution << 7 | \
                      self.shunt_adc_resolution << 3 | \
                      self.mode
        self.write(_REG_CONFIG, self.config)

    def getShuntVoltage_mV(self):
        self.write(_REG_CALIBRATION, self._cal_value)
        value = self.read(_REG_SHUNTVOLTAGE)
        if value > 32767:
            value -= 65535
        return value * 0.01

    def getBusVoltage_V(self):
        self.write(_REG_CALIBRATION, self._cal_value)
        self.read(_REG_BUSVOLTAGE)
        return (self.read(_REG_BUSVOLTAGE) >> 3) * 0.004

    def getCurrent_mA(self):
        value = self.read(_REG_CURRENT)
        if value > 32767:
            value -= 65535
        return value * self._current_lsb

    def getPower_W(self):
        self.write(_REG_CALIBRATION, self._cal_value)
        value = self.read(_REG_POWER)
        if value > 32767:
            value -= 65535
        return value * self._power_lsb


# =============================================================================
# OLED DISPLAY FUNCTIONS (from wpsd-oled.text.py)
# =============================================================================

def load_font(font_path, size):
    font = None
    try:
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, size)
        else:
            font = ImageFont.load_default()
    except Exception as e:
        font = ImageFont.load_default()
    if font is None:
        font = ImageFont.load_default()
    return font


def get_text_dimensions(text, font):
    try:
        dummy_img = Image.new('1', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        bbox = dummy_draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        try:
            width = font.getlength(text)
            bbox_a = dummy_draw.textbbox((0, 0), "A", font=font)
            height = bbox_a[3] - bbox_a[1] if bbox_a else 8
            return width, height
        except:
            return 0, 8


def get_oled_config_settings():
    screen_type, address, rotate_config_value = None, None, 0
    try:
        if not os.path.exists(OLED_CONFIG_PATH):
            print(f"Error: Config file not found: {OLED_CONFIG_PATH}", file=sys.stderr)
            return None, None, None

        config = configparser.ConfigParser()
        config.read(OLED_CONFIG_PATH)

        if not config.has_section("OLED"):
            print(f"Error: Missing [OLED] section in {OLED_CONFIG_PATH}", file=sys.stderr)
            return None, None, None

        if config.has_option("OLED", "Type"):
            try:
                type_int = config.getint("OLED", "Type")
                if type_int == 3:
                    screen_type, address = 'type3', 0x3C
                elif type_int == 6:
                    screen_type, address = 'type6', 0x3C
                else:
                    print(f"Warning: Unsupported OLED Type '{type_int}'. Check config.", file=sys.stderr)
            except ValueError:
                print(f"Warning: Invalid Type format in config. Must be an integer.", file=sys.stderr)
        else:
            print(f"Error: Missing 'Type' option in [OLED] section of {OLED_CONFIG_PATH}", file=sys.stderr)
            return None, None, None

        if config.has_option("OLED", "Address"):
            try:
                address = int(config.get("OLED", "Address"), 16)
            except ValueError:
                print(f"Warning: Invalid Address format in config. Using default: {address:#04x}", file=sys.stderr)

        if config.has_option("OLED", "Rotate"):
            try:
                rotate_config_value = config.getint("OLED", "Rotate")
                if rotate_config_value not in [0, 1]:
                    print(f"Warning: Invalid Rotate value '{rotate_config_value}'. Must be 0 or 1. Defaulting to 0.", file=sys.stderr)
                    rotate_config_value = 0
            except ValueError:
                print(f"Warning: Invalid Rotate format in config. Must be 0 or 1. Defaulting to 0.", file=sys.stderr)
                rotate_config_value = 0
        else:
            print(f"Info: 'Rotate' option not found in [OLED] section. Defaulting to 0 (no rotation).", file=sys.stderr)
            rotate_config_value = 0

        return screen_type, address, rotate_config_value

    except Exception as e:
        print(f"Error reading config: {e}", file=sys.stderr)
        return None, None, None


def clear_display(device):
    try:
        device.clear()
    except Exception as e:
        print(f"Error clearing display: {e}", file=sys.stderr)


def draw_text(device, line1, size1, line2, size2):
    try:
        width = device.width
        height = device.height
        font1 = load_font(DEFAULT_FONT_PATH, size1)
        font2 = load_font(DEFAULT_FONT_PATH, size2)
        image_mode = getattr(device, 'mode', '1')
        image = Image.new(image_mode, (width, height))
        draw = ImageDraw.Draw(image)

        text_width_1, text_height_1 = get_text_dimensions(line1, font1)
        text_width_2, text_height_2 = get_text_dimensions(line2, font2)

        x1 = max(0, (width - text_width_1) // 2)
        x2 = max(0, (width - text_width_2) // 2)

        total_h = text_height_1 + text_height_2
        spacing = max(1, (height - total_h) // 3)
        y1 = spacing
        y2 = y1 + text_height_1 + spacing
        if y2 + text_height_2 > height:
            spacing = max(0, (height - total_h) // 3)
            y1, y2 = spacing, y1 + text_height_1 + spacing
            if y2 + text_height_2 > height:
                y1, y2 = 0, text_height_1 + 1
                if y2 + text_height_2 > height:
                    y2 = height - text_height_2
                    y1 = max(0, y2 - text_height_1 - 1)

        draw.text((x1, y1), line1, font=font1, fill="white")
        draw.text((x2, y2), line2, font=font2, fill="white")
        device.display(image)
    except Exception as e:
        print(f"Error drawing text: {e}", file=sys.stderr)
        raise e


def init_oled_device():
    """Initialize the OLED device using config from /etc/mmdvmhost.
       Returns the luma OLED device object, or None on failure.
    """
    screen_type, address, rotate_config_value = get_oled_config_settings()
    if screen_type is None or address is None or rotate_config_value is None:
        print(f"Error: Failed to retrieve necessary OLED configuration from {OLED_CONFIG_PATH}. Exiting.", file=sys.stderr)
        return None

    rotation_value = 2 if rotate_config_value == 1 else 0

    try:
        serial = i2c(port=1, address=address)
        device_width, device_height = 128, 64

        if screen_type == 'type3':
            device = ssd1306(serial, width=device_width, height=device_height, rotate=rotation_value)
        elif screen_type == 'type6':
            device = sh1106(serial, width=device_width, height=device_height, rotate=rotation_value)
        else:
            print(f"Error: Invalid screen type '{screen_type}' determined from config.", file=sys.stderr)
            return None

        device.cleanup = lambda: None
        return device

    except FileNotFoundError:
        print(f"Error: I2C bus not found (is i2c enabled and device connected?).", file=sys.stderr)
        return None
    except OSError as e:
        print(f"Error communicating via I2C at address {address:#04x}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred initializing OLED: {e}", file=sys.stderr)
        return None


# =============================================================================
# UPS BATTERY MONITOR (from UPS.py)
# =============================================================================

def oled(device, line1="", line2="", size1=12, size2=12):
    """Send text to the OLED display directly (no subprocess needed)."""
    if device is not None:
        try:
            draw_text(device, line1, size1, line2, size2)
        except Exception as e:
            print(f"Warning: Could not update OLED display: {e}", file=sys.stderr)
    else:
        print("Warning: OLED device not available. Skipping display update.", file=sys.stderr)


def get_battery_percent(voltage, v_full, v_empty):
    """Calculate battery percentage from voltage, clamped to 0-100%."""
    if voltage > v_full:
        voltage = v_full
    if voltage < v_empty:
        voltage = v_empty

    return int(((voltage - v_empty) / (v_full - v_empty)) * 100)


def mains_present(current_ma, noise_threshold):
    """
    Positive current = charging = mains present.
    But ignore tiny currents (within noise_threshold) because they are noise.
    """
    if abs(current_ma) < noise_threshold:
        return True  # treat as no mains, no charging happening

    return current_ma > 0


def shutdown_pi():
    print("Battery low and no mains power. Shutting down...")
    os.system("sudo shutdown -h now")


def main():
    # Load battery settings from config file (falls back to defaults)
    ups_cfg = load_ups_config()
    v_full = ups_cfg["v_full"]
    v_empty = ups_cfg["v_empty"]
    low_battery_percent = ups_cfg["low_battery_percent"]
    noise_threshold = ups_cfg["current_noise_threshold"]

    print(f"UPS Monitor starting with: V_FULL={v_full}, V_EMPTY={v_empty}, "
          f"LOW_BATTERY_PERCENT={low_battery_percent}, "
          f"CURRENT_NOISE_THRESHOLD={noise_threshold}")

    # Initialize INA219 at correct address
    ina = INA219(addr=0x43)

    # Initialize the OLED display device
    oled_device = init_oled_device()
    if oled_device is None:
        print("Warning: OLED display could not be initialized. Continuing without display.", file=sys.stderr)

    while True:
        bus_voltage = ina.getBusVoltage_V()
        current_ma = ina.getCurrent_mA()

        battery_percent = get_battery_percent(bus_voltage, v_full, v_empty)

        print(f"Voltage: {bus_voltage:.2f} V | Current: {current_ma:.0f} mA | Battery: {battery_percent}%")

        if mains_present(current_ma, noise_threshold):
            print("Mains power detected (charging).")
        else:
            print("Running on battery power (discharging).")
            oled(
                oled_device,
                line1=f"Running on Bat",
                line2=f"Battery: {battery_percent}%",
                size1=14,
                size2=12
            )
            if battery_percent <= low_battery_percent:
                oled(oled_device, "LOW BATTERY", "SHUTTING DOWN", size1=14, size2=14)
                shutdown_pi()

        time.sleep(120)


if __name__ == "__main__":
    main()
