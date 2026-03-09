# code.py
# ──────────────────────────────────────────────
# Adafruit MacroPad media controller
# Handles: play/pause, next, previous, vol up/down, mute
# ──────────────────────────────────────────────

# ── Imports ───────────────────────────────────
import board                          # pin definitions for this specific board
import busio                          # I2C / SPI communication
import displayio                      # display graphics system
import terminalio                     # built-in font
import usb_hid                        # allows board to act as USB HID device (keyboard, mouse, etc)
import time

from adafruit_macropad import MacroPad                        # type: ignore # high-level MacroPad helper
from adafruit_hid.consumer_control import ConsumerControl     # type: ignore # sends media keys
from adafruit_hid.consumer_control_code import ConsumerControlCode  # type: ignore # media key codes
from adafruit_display_text import label                       # type: ignore # text on OLED

SLEEP_TIMEOUT = 5           #Seconds
LOW_PIXEL_BRIGHTNESS = 0x2F
HIGH_PIXEL_BRIGHTNESS = 0xAF
BRIGHTNESS_LIMITER = 0.2 # overall dimming


last_activity = time.monotonic()
sleeping = False


# ── Hardware Init ─────────────────────────────
macropad = MacroPad()                 # sets up keys, encoder, neopixels, OLED all at once
cc = ConsumerControl(usb_hid.devices) # init the HID consumer control (media keys)


# ── Display Setup ─────────────────────────────
# MacroPad OLED is 128x64, uses displayio
display = macropad.display
display.rotation = 0

# Create a displayio group (like a canvas) to hold all text elements
splash = displayio.Group()
display.root_group = splash

# Title label at top of screen
title = label.Label(
    terminalio.FONT,
    text="MEDIA CONTROL",
    color=0xFFFFFF,
    x=10,
    y=6
)
splash.append(title)

# Key hint labels along the bottom
hint = label.Label(
    terminalio.FONT,
    text="<<  Pause  >>",
    color=0x888888,
    x=10,
    y=50
)
splash.append(hint)

def dim_color(hex_color, brightness):
    r = (hex_color >> 16) & 0xFF
    g = (hex_color >> 8) & 0xFF
    b = (hex_color) & 0xFF

    dim_factor = (brightness/0xFF)
    r = int(r * dim_factor)
    g = int(g * dim_factor)
    b = int(b * dim_factor)

    return (r << 16) | (g << 8) | b


# functions to go into and out of 'sleep mode'
# Dim LEDs, turn off LCD screen
def go_to_sleep():
    global sleeping
    draw_pixels(LOW_PIXEL_BRIGHTNESS)
    display.brightness = 0
    sleeping = True

def wake_up():
    global sleeping, last_activity
    draw_pixels(HIGH_PIXEL_BRIGHTNESS)
    display.brightness = 0.2
    last_activity = time.monotonic()
    sleeping = False

def input_received():
    global sleeping, last_activity 
    last_activity = time.monotonic()
    if sleeping:
        wake_up()


# ── Neopixel Setup ────────────────────────────
# Light up only the assigned keys, others off
def draw_pixels(brightness = 0xFF):
    off_color = 0x7F002F # pink
    for i in range(12):
        if KEY_MAP[i] is not None:
            macropad.pixels[i] = dim_color(KEY_MAP[i][2], brightness)  # set to assigned color
        else:
            macropad.pixels[i] = dim_color(off_color, brightness) 


# ── Key Mapping ───────────────────────────────
# MacroPad has 12 keys arranged in a 3x4 grid:
#   0  1  2
#   3  4  5
#   6  7  8
#   9  10 11
#
# Each entry is (ConsumerControlCode, display_name, neopixel_color)
# None means the key does nothing

KEY_MAP = {
    0:  (ConsumerControlCode.SCAN_PREVIOUS_TRACK, "Previous",  0x0000FF),  # blue
    1:  (ConsumerControlCode.PLAY_PAUSE,          "Play/Pause",0x00FF00),  # green
    2:  (ConsumerControlCode.SCAN_NEXT_TRACK,     "Next",      0x0000FF),  # blue
    3:  None,
    4:  None,
    5:  None,
    6:  None,
    7:  None,
    8:  None,
    9:  None,
    10: None,
    11: None,
}

draw_pixels()
macropad.pixels.brightness = BRIGHTNESS_LIMITER


# ── Encoder State ─────────────────────────────
# We'll use the encoder for volume scrubbing
last_encoder_pos = macropad.encoder


# ── Main Loop ─────────────────────────────────
while True:

    # -- Check key events --
    # macropad.keys.events is a queue of press/release events
    event = macropad.keys.events.get()

    if event:
        key_num = event.key_number

        if event.pressed:
            mapping = KEY_MAP.get(key_num)

            if mapping is not None:
                input_received()
                code, name, color = mapping

                # Flash the key white briefly to give tactile feedback on screen
                macropad.pixels[key_num] = 0xFFFFFF

                # Send the HID consumer control code to the host computer
                cc.send(code)


        if event.released:
            input_received()
            # Restore original pixel color on release
            mapping = KEY_MAP.get(key_num)
            if mapping is not None:
                macropad.pixels[key_num] = mapping[2]
            else:
                macropad.pixels[key_num] = off_color

    # -- Check rotary encoder for volume scrub --
    current_pos = macropad.encoder
    if current_pos != last_encoder_pos:
        input_received()
        delta = current_pos - last_encoder_pos
        
        if delta > 0:
            # Turned right = volume up
            for _ in range(abs(delta)):
                cc.send(ConsumerControlCode.VOLUME_INCREMENT)
        else:
            # Turned left = volume down
            for _ in range(abs(delta)):
                cc.send(ConsumerControlCode.VOLUME_DECREMENT)

        last_encoder_pos = current_pos

    # -- Check encoder button for mute --
    # macropad.encoder_switch is True when pressed
    macropad.encoder_switch_debounced.update()
    if macropad.encoder_switch_debounced.pressed:
        input_received()
        cc.send(ConsumerControlCode.MUTE)

    if not sleeping and (time.monotonic() - last_activity > SLEEP_TIMEOUT):
        go_to_sleep()