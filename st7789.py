# st7789.py - High-Performance ST7789 Display Driver for RP2350-Touch-LCD-2.8
from machine import Pin, SPI, PWM
import time
import framebuf

# 16-bit RGB565 Colors (in RP2040/RP2350 byte order for framebuf.RGB565)
def rgb(r, g, b):
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | ((c >> 8) & 0xFF)

BLACK       = rgb(0, 0, 0)
WHITE       = rgb(255, 255, 255)
NAVY        = rgb(15, 23, 42)
HEADER_BG   = rgb(30, 41, 59)
SEARCH_BG   = rgb(241, 245, 249)
TEXT_DARK   = rgb(15, 23, 42)
TEXT_MUTED  = rgb(100, 116, 139)
ACCENT_BLUE = rgb(37, 99, 235)
ACCENT_CYAN = rgb(6, 182, 212)
KEY_BG      = rgb(255, 255, 255)
KEY_ACTIVE  = rgb(199, 210, 254)
KEY_BORDER  = rgb(203, 213, 225)
KEY_SPECIAL = rgb(226, 232, 240)
RESULT_BG   = rgb(248, 250, 252)
SUGG_BG     = rgb(238, 242, 255)
SUGG_BORDER = rgb(199, 210, 254)
SUGG_TEXT   = rgb(67, 56, 202)
SPEAK_BG    = rgb(16, 185, 129)
SPEAK_BORDER= rgb(5, 150, 105)
GREEN       = rgb(22, 163, 74)
RED         = rgb(220, 38, 38)
GRAY        = rgb(148, 163, 184)
LIGHT_GRAY  = rgb(226, 232, 240)

class ST7789:
    def __init__(self, width=320, height=240, 
                 spi_id=1, sck=10, mosi=11, cs=13, dc=14, rst=15, bl=16,
                 baudrate=62_500_000):
        self.width = width
        self.height = height
        
        self.dc = Pin(dc, Pin.OUT)
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.rst = Pin(rst, Pin.OUT, value=1)
        
        # Backlight PWM on GPIO 16
        self.bl = PWM(Pin(bl))
        self.bl.freq(5000)
        self.set_brightness(100)
        
        # SPI1 on RP2350 (up to 62.5MHz)
        self.spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                       sck=Pin(sck), mosi=Pin(mosi))
        
        # Framebuffer (320x240 RGB565 = 153,600 bytes)
        self.buffer = bytearray(self.width * self.height * 2)
        self.fb = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.RGB565)
        
        self.init_display()

    def write_cmd(self, cmd):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, data):
        self.cs(0)
        self.dc(1)
        if isinstance(data, int):
            self.spi.write(bytearray([data]))
        else:
            self.spi.write(data)
        self.cs(1)

    def set_brightness(self, percent):
        p = max(0, min(100, percent))
        duty = int(65535 * p / 100)
        self.bl.duty_u16(duty)

    def reset(self):
        self.rst(0)
        time.sleep_ms(15)
        self.rst(1)
        time.sleep_ms(50)

    def init_display(self):
        self.reset()
        
        self.write_cmd(0x01) # SWRESET
        time.sleep_ms(150)
        self.write_cmd(0x11) # SLPOUT
        time.sleep_ms(120)

        self.write_cmd(0x36) # MADCTL
        self.write_data(0x70) # Landscape 320x240 (MX=0, MY=1, MV=1)

        self.write_cmd(0x3A) # COLMOD
        self.write_data(0x05) # 16-bit RGB565

        self.write_cmd(0xB2) # PORCTRL
        self.write_data(bytearray([0x0B, 0x0B, 0x00, 0x33, 0x35]))

        self.write_cmd(0xB7) # GCTRL
        self.write_data(0x11)

        self.write_cmd(0xBB) # VCOMS
        self.write_data(0x35)

        self.write_cmd(0xC0) # LCMCTRL
        self.write_data(0x2C)

        self.write_cmd(0xC2) # VDVVRHEN
        self.write_data(0x01)

        self.write_cmd(0xC3) # VRHS
        self.write_data(0x0D)

        self.write_cmd(0xC4) # VDVS
        self.write_data(0x20)

        self.write_cmd(0xC6) # FRCTRL2
        self.write_data(0x13)

        self.write_cmd(0xD0) # PWCTRL1
        self.write_data(bytearray([0xA4, 0xA1]))

        self.write_cmd(0x21) # INVON
        self.write_cmd(0x29) # DISPON
        time.sleep_ms(50)

        # Set drawing window to full screen
        self.set_window(0, 0, self.width - 1, self.height - 1)

    def set_window(self, x0, y0, x1, y1):
        self.write_cmd(0x2A) # CASET
        self.write_data(bytearray([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self.write_cmd(0x2B) # RASET
        self.write_data(bytearray([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
        self.write_cmd(0x2C) # RAMWR

    def show(self):
        """Flushes the 153KB framebuffer to display via high-speed SPI."""
        self.set_window(0, 0, self.width - 1, self.height - 1)
        self.cs(0)
        self.dc(1)
        self.spi.write(self.buffer)
        self.cs(1)

    def flush_rect(self, x, y, w, h):
        """Flushes only a specific rectangular region of the framebuffer to display (Ultra Fast)."""
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        if w <= 0 or h <= 0 or x >= self.width or y >= self.height:
            return
        x1 = min(self.width - 1, x + w - 1)
        y1 = min(self.height - 1, y + h - 1)
        
        self.set_window(x, y, x1, y1)
        self.cs(0)
        self.dc(1)
        
        mv = memoryview(self.buffer)
        row_len = (x1 - x + 1) * 2
        for r in range(y, y1 + 1):
            offset = (r * self.width + x) * 2
            self.spi.write(mv[offset : offset + row_len])
        self.cs(1)

    # FrameBuffer delegation
    def fill(self, color):
        self.fb.fill(color)

    def pixel(self, x, y, color):
        self.fb.pixel(x, y, color)

    def hline(self, x, y, w, color):
        self.fb.hline(x, y, w, color)

    def vline(self, x, y, h, color):
        self.fb.vline(x, y, h, color)

    def rect(self, x, y, w, h, color):
        self.fb.rect(x, y, w, h, color)

    def fill_rect(self, x, y, w, h, color):
        self.fb.fill_rect(x, y, w, h, color)
