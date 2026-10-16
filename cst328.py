# cst328.py - Capacitive Touch Driver (CST328 / CST3530) for RP2350-Touch-LCD-2.8
from machine import Pin, I2C
import time

class CST328:
    MAX_POINTS = 5
    DATA_REG = 0xD0070000
    END_READ_REG = 0xD00002AB
    COORD_NEXT_REG = 0xD0070900

    def __init__(self, i2c=None, width=320, height=240,
                 scl=7, sda=6, rst=17, int_pin=18, bat_en=26, rotation=1):
        self.width = width
        self.height = height
        self.rotation = rotation # 1: Landscape 320x240
        self.points = 0
        self.coords = []
        self.read_flag = False

        # Power enable on RP2350
        if bat_en is not None:
            try:
                self.bat_en = Pin(bat_en, Pin.OUT, value=1)
            except Exception:
                pass

        self.rst = Pin(rst, Pin.OUT, value=1)
        self.int = Pin(int_pin, Pin.IN, Pin.PULL_UP)
        
        # Hardware interrupt on touch
        try:
            self.int.irq(handler=self._irq_handler, trigger=Pin.IRQ_FALLING)
        except Exception:
            pass

        if i2c is None:
            self.i2c = I2C(1, scl=Pin(scl), sda=Pin(sda), freq=400_000)
        else:
            self.i2c = i2c

        self.reset()
        
        # Auto-detect I2C address
        scan = self.i2c.scan()
        if 0x1A in scan:
            self.device_addr = 0x1A
        elif 0x58 in scan:
            self.device_addr = 0x58
        else:
            self.device_addr = 0x1A

    def _irq_handler(self, pin):
        self.read_flag = True

    def reset(self):
        self.rst(0)
        time.sleep_ms(15)
        self.rst(1)
        time.sleep_ms(50)

    def _reg_bytes(self, reg):
        return bytes([
            (reg >> 24) & 0xFF,
            (reg >> 16) & 0xFF,
            (reg >> 8) & 0xFF,
            reg & 0xFF,
        ])

    def read_touch(self):
        """Polls or checks for touch contact."""
        if not self.read_flag and self.int.value() != 0:
            return False
        self.read_flag = False

        self.coords = []
        self.points = 0

        # Method 1: CST328 16-bit register format (0xD000)
        try:
            data = self.i2c.readfrom_mem(self.device_addr, 0xD000, 7, addrsize=16)
            if data and (data[0] & 0x0F == 0x06 or (data[5] & 0x0F) > 0 or data[6] == 0xAB):
                rx = (data[1] << 4) | ((data[3] >> 4) & 0x0F)
                ry = (data[2] << 4) | (data[3] & 0x0F)
                px, py = self._map_coordinates(rx, ry)
                self.coords = [{"x": px, "y": py, "pressure": data[4]}]
                self.points = 1
                return True
        except Exception:
            pass

        # Method 2: CST3530 32-bit register format
        try:
            self.i2c.writeto(self.device_addr, self._reg_bytes(self.DATA_REG), False)
            buf = bytearray(self.i2c.readfrom(self.device_addr, 9))
            
            if ((buf[3] & 0x0F) != 0x00) and ((buf[8] & 0xF0) != 0x00):
                pts = min(self.MAX_POINTS, buf[3] & 0x0F)
                if pts > 1:
                    self.i2c.writeto(self.device_addr, self._reg_bytes(self.COORD_NEXT_REG), False)
                    extra = self.i2c.readfrom(self.device_addr, (pts - 1) * 5)
                    buf.extend(extra)
                    
                self.i2c.writeto(self.device_addr, self._reg_bytes(self.END_READ_REG))

                for i in range(pts):
                    rx = ((buf[(i * 5) + 7] & 0x0F) << 8) + buf[(i * 5) + 4]
                    ry = ((buf[(i * 5) + 7] & 0xF0) << 4) + buf[(i * 5) + 5]
                    pressure = buf[(i * 5) + 6]
                    px, py = self._map_coordinates(rx, ry)
                    self.coords.append({"x": px, "y": py, "pressure": pressure})
                self.points = len(self.coords)
                return self.points > 0
            else:
                self.i2c.writeto(self.device_addr, self._reg_bytes(self.END_READ_REG))
        except Exception:
            pass

        return False

    def _map_coordinates(self, x, y):
        """Converts native 240x320 portrait touch to Landscape 320x240."""
        if self.rotation == 1:
            sx = y
            sy = 239 - x
        elif self.rotation == 3:
            sx = 319 - y
            sy = x
        elif self.rotation == 2:
            sx = 239 - x
            sy = 319 - y
        else: # Rotation 0 (Portrait)
            sx = x
            sy = y
            
        sx = max(0, min(self.width - 1, sx))
        sy = max(0, min(self.height - 1, sy))
        return sx, sy

    def get_touch(self):
        """Returns single (x, y) tuple if touched, or None."""
        if self.read_touch() and self.coords:
            return self.coords[0]["x"], self.coords[0]["y"]
        return None
