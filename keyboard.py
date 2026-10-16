# keyboard.py - Virtual Touch Keyboard for 320x240 LCD
import fonts
from st7789 import (
    rgb, WHITE, BLACK, TEXT_DARK, KEY_BG, KEY_ACTIVE, 
    KEY_BORDER, KEY_SPECIAL, ACCENT_BLUE, ACCENT_CYAN, GREEN
)

class VirtualKeyboard:
    def __init__(self, y_start=138, height=100):
        self.y_start = y_start
        self.height = height
        self.is_english = True # True: English, False: Hebrew
        self.active_key = None
        
        # Build layouts
        self.en_rows = [
            ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
            ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
            ["z", "x", "c", "v", "b", "n", "m"],
        ]
        
        # Israeli Hebrew keyboard layout
        self.he_rows = [
            ["ק", "ר", "א", "ט", "ו", "ן", "ם", "פ"],
            ["ש", "ד", "ג", "כ", "ע", "י", "ח", "ל", "ך", "ף"],
            ["ז", "ס", "ב", "ה", "נ", "מ", "צ", "ת", "ץ"],
        ]
        
        self.keys = []
        self.build_key_rects()

    def toggle_language(self):
        self.is_english = not self.is_english
        self.build_key_rects()

    def build_key_rects(self):
        self.keys = []
        rows = self.en_rows if self.is_english else self.he_rows
        
        # Layout metrics for 320px width
        y = self.y_start
        row_h = 23
        spacing = 2
        
        # Rows 1 to 3
        for r_idx, row in enumerate(rows):
            num_keys = len(row)
            total_spacing = (num_keys + 1) * spacing
            avail_w = 320 - total_spacing
            k_w = avail_w // num_keys
            x_offset = (320 - (num_keys * k_w + (num_keys - 1) * spacing)) // 2
            
            for c_idx, ch in enumerate(row):
                kx = x_offset + c_idx * (k_w + spacing)
                ky = y + r_idx * (row_h + spacing)
                self.keys.append({
                    "type": "char",
                    "value": ch,
                    "label": ch.upper() if self.is_english else ch,
                    "x": kx, "y": ky, "w": k_w, "h": row_h,
                    "is_special": False
                })
                
        # Bottom row 4: [LANG] [SPACE] [DEL] [GO]
        b_y = y + 3 * (row_h + spacing)
        # 1. Lang switch button
        self.keys.append({
            "type": "lang",
            "value": "LANG",
            "label": "עב" if self.is_english else "EN",
            "x": 4, "y": b_y, "w": 48, "h": row_h,
            "is_special": True
        })
        # 2. Space button
        self.keys.append({
            "type": "char",
            "value": " ",
            "label": "SPACE" if self.is_english else "רווח",
            "x": 56, "y": b_y, "w": 146, "h": row_h,
            "is_special": False
        })
        # 3. Backspace button
        self.keys.append({
            "type": "backspace",
            "value": "BKSP",
            "label": "<",
            "x": 206, "y": b_y, "w": 40, "h": row_h,
            "is_special": True
        })
        # 4. Search / GO button
        self.keys.append({
            "type": "search",
            "value": "SEARCH",
            "label": "GO",
            "x": 250, "y": b_y, "w": 66, "h": row_h,
            "is_special": True
        })

    def draw_key(self, display, k, is_pressed=False, flush=True):
        """Draws and optionally flushes a single key for ultra-fast visual feedback."""
        if is_pressed:
            bg = KEY_ACTIVE
            border = ACCENT_BLUE
            fg = ACCENT_BLUE
        elif k["type"] == "search":
            bg = ACCENT_BLUE
            border = ACCENT_BLUE
            fg = WHITE
        elif k["is_special"]:
            bg = KEY_SPECIAL
            border = KEY_BORDER
            fg = TEXT_DARK
        else:
            bg = KEY_BG
            border = KEY_BORDER
            fg = TEXT_DARK
            
        x, y, w, h = k["x"], k["y"], k["w"], k["h"]
        display.fill_rect(x + 1, y + 1, w - 2, h - 2, bg)
        display.rect(x, y, w, h, border)
        
        lbl = k["label"]
        lbl_len = len(lbl)
        lbl_w = lbl_len * fonts.WIDTH
        text_x = x + (w - lbl_w) // 2
        text_y = y + (h - fonts.HEIGHT) // 2
        fonts.draw_text(display, lbl, text_x, text_y, fg, bg=bg)
        
        if flush and hasattr(display, 'flush_rect'):
            display.flush_rect(x, y, w, h)

    def draw(self, display, active_key_obj=None):
        """Draws all keys directly to the display framebuffer."""
        display.fill_rect(0, self.y_start - 2, 320, self.height + 2, KEY_SPECIAL)
        display.hline(0, self.y_start - 2, 320, KEY_BORDER)
        for k in self.keys:
            self.draw_key(display, k, is_pressed=(active_key_obj is not None and k == active_key_obj), flush=False)

    def handle_touch(self, tx, ty):
        """Returns the key object touched at (tx, ty), or None."""
        if ty < self.y_start:
            return None
        for k in self.keys:
            if k["x"] <= tx <= k["x"] + k["w"] and k["y"] <= ty <= k["y"] + k["h"]:
                return k
        return None
