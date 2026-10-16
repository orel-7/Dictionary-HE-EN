# sdcard.py - MicroPython SPI SD Card driver
from micropython import const
import time

_CMD_TIMEOUT = const(100)
_R1_IDLE_STATE = const(1 << 0)
_R1_ILLEGAL_COMMAND = const(1 << 2)

class SDCard:
    def __init__(self, spi, cs, baudrate=1320000):
        self.spi = spi
        self.cs = cs
        self.cmdbuf = bytearray(6)
        self.dummybuf = bytearray(512)
        self.tokenbuf = bytearray(1)
        for i in range(512):
            self.dummybuf[i] = 0xFF
        self.dummybuf_memoryview = memoryview(self.dummybuf)
        self.init_card(baudrate)

    def init_card(self, baudrate):
        self.cs.init(self.cs.OUT, value=1)
        self.spi.init(baudrate=100000, polarity=0, phase=0)
        
        # Clock at least 74 dummy cycles
        for _ in range(16):
            self.spi.write(b"\xff")
            
        # CMD0: go idle state
        for _ in range(5):
            if self.cmd(0, 0, 0x95) == _R1_IDLE_STATE:
                break
        else:
            raise OSError("No SD card responded to CMD0")
            
        # CMD8: determine card version
        r = self.cmd(8, 0x01AA, 0x87, 4)
        if r == _R1_IDLE_STATE:
            # SD v2+
            for _ in range(_CMD_TIMEOUT):
                time.sleep_ms(50)
                self.cmd(55, 0, 0)
                if self.cmd(41, 0x40000000, 0) == 0:
                    break
            else:
                raise OSError("SD card init timeout")
                
            # CMD58: read OCR
            if self.cmd(58, 0, 0, 4) != 0:
                raise OSError("SD card read OCR failed")
            self.cdv = 1 if (self.tokenbuf[0] & 0x40) else 512
        else:
            # SD v1 / MMC
            for _ in range(_CMD_TIMEOUT):
                time.sleep_ms(50)
                self.cmd(55, 0, 0)
                if self.cmd(41, 0, 0) == 0:
                    break
            else:
                raise OSError("SD v1 init timeout")
            self.cdv = 512

        # Set block length to 512
        if self.cmd(16, 512, 0) != 0:
            raise OSError("SD set blocklen failed")
            
        # Speed up SPI
        self.spi.init(baudrate=baudrate, polarity=0, phase=0)

    def cmd(self, cmd, arg, crc, final=0):
        self.cs(0)
        self.cmdbuf[0] = 0x40 | cmd
        self.cmdbuf[1] = arg >> 24
        self.cmdbuf[2] = arg >> 16
        self.cmdbuf[3] = arg >> 8
        self.cmdbuf[4] = arg
        self.cmdbuf[5] = crc
        self.spi.write(self.cmdbuf)

        for _ in range(_CMD_TIMEOUT):
            self.spi.readinto(self.tokenbuf, 0xFF)
            response = self.tokenbuf[0]
            if not (response & 0x80):
                for _ in range(final):
                    self.spi.readinto(self.tokenbuf, 0xFF)
                self.spi.write(b"\xff")
                self.cs(1)
                return response

        self.cs(1)
        self.spi.write(b"\xff")
        return -1

    def readblocks(self, block_num, buf):
        nblocks = len(buf) // 512
        for i in range(nblocks):
            if self.cmd(17, block_num + i, 0) != 0:
                raise OSError(5) # EIO
            # Wait for data token
            while self.tokenbuf[0] != 0xFE:
                self.spi.readinto(self.tokenbuf, 0xFF)
            self.spi.readinto(memoryview(buf)[i * 512 : (i + 1) * 512], 0xFF)
            self.spi.read(2) # CRC
            self.cs(1)
            self.spi.write(b"\xff")

    def count(self):
        return 0 # Auto-handled by vfs
