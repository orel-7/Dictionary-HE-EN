# xpt2046.py - XPT2046 Resistive Touch Controller for Waveshare Pico-ResTouch-LCD-2.8
from machine import Pin, SPI
import time

class XPT2046:
    def __init__(self, spi=None, cs=16, irq=17, 
                 width=320, height=240,
                 cal_x_min=300, cal_x_max=3800,
                 cal_y_min=250, cal_y_max=3800):
        self.width = width
        self.height = height
        
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.irq = Pin(irq, Pin.IN, Pin.PULL_UP)
        
        if spi is None:
            self.spi = SPI(1, baudrate=2_000_000, polarity=0, phase=0,
                           sck=Pin(10), mosi=Pin(11), miso=Pin(12))
        else:
            self.spi = spi
            
        self.cal_x_min = cal_x_min
        self.cal_x_max = cal_x_max
        self.cal_y_min = cal_y_min
        self.cal_y_max = cal_y_max

    def is_touched(self):
        """Returns True if the screen is actively touched."""
        return self.irq.value() == 0

    def _read_raw_channel(self, cmd):
        self.cs.value(0)
        self.spi.write(bytearray([cmd]))
        raw = self.spi.read(2)
        self.cs.value(1)
        # 12-bit value
        return ((raw[0] << 8) | raw[1]) >> 3

    def get_raw_touch(self):
        """Reads raw ADC touch coordinates with multi-sampling filter."""
        if not self.is_touched():
            return None
            
        samples_x = []
        samples_y = []
        
        for _ in range(3):
            # 0x90 = Read X (differential 12-bit)
            # 0xD0 = Read Y (differential 12-bit)
            rx = self._read_raw_channel(0x90)
            ry = self._read_raw_channel(0xD0)
            if 100 < rx < 4000 and 100 < ry < 4000:
                samples_x.append(rx)
                samples_y.append(ry)
                
        if not samples_x:
            return None
            
        # Median / average
        avg_x = sum(samples_x) // len(samples_x)
        avg_y = sum(samples_y) // len(samples_y)
        return avg_x, avg_y

    def get_touch(self):
        """
        Returns (x, y) in screen pixel coordinates (0..319, 0..239), or None if not touched.
        """
        raw = self.get_raw_touch()
        if raw is None:
            return None
            
        rx, ry = raw
        
        # Mapping for Landscape 320x240 orientation
        # On Waveshare 2.8" LCD in landscape mode:
        # Screen X (0..319) maps from raw Y (cal_y_min..cal_y_max)
        # Screen Y (0..239) maps from raw X (cal_x_max..cal_x_min)
        
        # Clamp
        rx = max(self.cal_x_min, min(self.cal_x_max, rx))
        ry = max(self.cal_y_min, min(self.cal_y_max, ry))
        
        # Calculate pixel coordinates
        px = int((ry - self.cal_y_min) * (self.width - 1) / (self.cal_y_max - self.cal_y_min))
        py = int((self.cal_x_max - rx) * (self.height - 1) / (self.cal_x_max - self.cal_x_min))
        
        # Bounds check
        px = max(0, min(self.width - 1, px))
        py = max(0, min(self.height - 1, py))
        
        return px, py
