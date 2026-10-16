# main.py - Bilingual Pocket Dictionary (Milonit) for RP2350-Touch-LCD-2.8
import time
import os
import gc
from machine import Pin, SPI

from st7789 import (
    ST7789, rgb, BLACK, WHITE, NAVY, HEADER_BG, SEARCH_BG,
    TEXT_DARK, TEXT_MUTED, ACCENT_BLUE, ACCENT_CYAN,
    KEY_BORDER, KEY_BG, KEY_ACTIVE, KEY_SPECIAL,
    RESULT_BG, SUGG_BG, SUGG_BORDER, SUGG_TEXT,
    SPEAK_BG, SPEAK_BORDER, GREEN, RED, GRAY, LIGHT_GRAY
)
from cst328 import CST328
from audio import AudioManager
from dictionary import BilingualDictionary
from keyboard import VirtualKeyboard
import fonts

class MilonitApp:
    def __init__(self):
        print("Starting Milonit on Waveshare RP2350-Touch-LCD-2.8...")
        
        # 1. Power enable for RP2350 (BAT_EN)
        try:
            self.bat_en = Pin(26, Pin.OUT, value=1)
        except Exception:
            pass

        # 2. Initialize Display (High-Speed SPI 62.5MHz with 153KB FrameBuffer)
        self.display = ST7789(width=320, height=240)
        
        # 3. Mount MicroSD Card if inserted
        self.mount_sd_card()
        
        # 4. Initialize CST328 Capacitive Touch Controller
        self.touch = CST328(width=320, height=240, rotation=1)
        
        # 5. Initialize I2S Audio & Speech Synthesizer
        self.audio = AudioManager(sck=2, ws=3, sd=4, rate=16000)
        
        # 6. Initialize Binary Indexed Bilingual Dictionary
        self.dict = BilingualDictionary()
        print(f"Loaded Dictionary: {self.dict.en_count} EN, {self.dict.he_count} HE words.")
        
        # 7. Initialize Virtual Keyboard
        self.kb = VirtualKeyboard(y_start=138, height=100)
        
        # 8. State
        self.input_text = ""
        self.definition = None
        self.suggestions = []
        self.suggestion_rects = []
        self.status = f"מוכן ({self.dict.en_count + self.dict.he_count})"
        self.needs_redraw = True
        self.active_key = None
        
        # Interactive UI Buttons
        self.btn_mode = {"x": 4, "y": 3, "w": 82, "h": 22}
        self.btn_vol  = {"x": 218, "y": 3, "w": 52, "h": 22}
        self.btn_clear= {"x": 274, "y": 3, "w": 42, "h": 22}
        self.btn_speak= {"x": 228, "y": 66, "w": 82, "h": 20}
        
        # Initial greeting sound
        self.audio.play_tone(600, 0.06)

    def mount_sd_card(self):
        """Mounts MicroSD card if present, otherwise uses internal 16MB flash."""
        try:
            from sdcard import SDCard
            spi0 = SPI(0, baudrate=10_000_000, polarity=0, phase=0,
                       sck=Pin(18), mosi=Pin(19), miso=Pin(16))
            sd_cs = Pin(22, Pin.OUT, value=1)
            sd = SDCard(spi0, sd_cs)
            os.mount(sd, "/sd")
            print("Mounted MicroSD card at /sd successfully.")
        except Exception as e:
            print("SD card not present or mount bypassed (using high-speed internal flash).")

    def toggle_mode(self):
        self.kb.toggle_language()
        self.input_text = ""
        self.definition = None
        self.suggestions = []
        self.suggestion_rects = []
        self.status = "EN -> עב" if self.kb.is_english else "עב -> EN"
        self.audio.play_click()
        self.needs_redraw = True

    def cycle_volume(self):
        new_vol = self.audio.cycle_volume()
        self.status = f"Vol: {new_vol}/10" if new_vol > 0 else "Mute"
        self.needs_redraw = True

    def speak_current_word(self):
        """Speaks English word (either query or translation)."""
        target = ""
        if self.kb.is_english:
            target = self.input_text.strip()
        elif self.definition:
            # First English definition word
            target = self.definition.split(',')[0].split(';')[0].strip()
        
        if target:
            # Highlight speak button visually
            self.display.fill_rect(self.btn_speak["x"], self.btn_speak["y"], 
                                   self.btn_speak["w"], self.btn_speak["h"], WHITE)
            self.display.show()
            self.audio.speak_word(target)
            self.needs_redraw = True

    def perform_search(self, word=None):
        query = word if word is not None else self.input_text.strip()
        if not query:
            self.definition = None
            self.suggestions = []
            self.suggestion_rects = []
            self.status = "הקלד מילה לחיפוש" if not self.kb.is_english else "Type a word"
            self.needs_redraw = True
            return

        self.input_text = query
        self.status = "מחפש..." if not self.kb.is_english else "Searching..."
        self.draw_ui()

        defn, suggs = self.dict.lookup(query, is_english=self.kb.is_english)
        self.definition = defn
        self.suggestions = suggs
        self.suggestion_rects = []
        
        if defn:
            self.status = "נמצא!" if not self.kb.is_english else "Found!"
            self.audio.play_chime()
        elif suggs:
            self.status = "שגיאת כתיב?" if not self.kb.is_english else "Typo? Suggestions:"
            self.audio.play_typo()
        else:
            self.status = "לא נמצא" if not self.kb.is_english else "Not found"
            self.audio.play_typo()
            
        self.needs_redraw = True

    def draw_top_bar(self):
        # Header bar background
        self.display.fill_rect(0, 0, 320, 28, HEADER_BG)
        
        # 1. Mode button [EN -> עב] or [עב -> EN]
        mx, my, mw, mh = self.btn_mode["x"], self.btn_mode["y"], self.btn_mode["w"], self.btn_mode["h"]
        self.display.fill_rect(mx, my, mw, mh, ACCENT_BLUE)
        self.display.rect(mx, my, mw, mh, WHITE)
        mode_label = "EN -> עב" if self.kb.is_english else "עב -> EN"
        fonts.draw_text(self.display, mode_label, mx + 6, my + 4, WHITE, bg=ACCENT_BLUE)
        
        # 2. Status message
        fonts.draw_text(self.display, self.status, 90, 7, LIGHT_GRAY, bg=HEADER_BG, max_width=124)
        
        # 3. Volume button [🔊 7] / [🔇 0]
        vx, vy, vw, vh = self.btn_vol["x"], self.btn_vol["y"], self.btn_vol["w"], self.btn_vol["h"]
        v_bg = rgb(51, 65, 85) if self.audio.volume > 0 else rgb(153, 27, 27)
        self.display.fill_rect(vx, vy, vw, vh, v_bg)
        self.display.rect(vx, vy, vw, vh, WHITE)
        vol_label = f"V:{self.audio.volume}" if self.audio.volume > 0 else "MUTE"
        fonts.draw_text(self.display, vol_label, vx + 6, vy + 4, WHITE, bg=v_bg)
        
        # 4. Clear button [CLR]
        cx, cy, cw, ch = self.btn_clear["x"], self.btn_clear["y"], self.btn_clear["w"], self.btn_clear["h"]
        self.display.fill_rect(cx, cy, cw, ch, rgb(71, 85, 105))
        self.display.rect(cx, cy, cw, ch, WHITE)
        fonts.draw_text(self.display, "CLR", cx + 7, cy + 4, WHITE, bg=rgb(71, 85, 105))

    def draw_search_box(self):
        # Search input box
        box_x, box_y, box_w, box_h = 4, 32, 312, 26
        self.display.fill_rect(box_x, box_y, box_w, box_h, SEARCH_BG)
        self.display.rect(box_x, box_y, box_w, box_h, KEY_BORDER)
        
        disp_txt = self.input_text
        if not disp_txt:
            placeholder = "Type in English..." if self.kb.is_english else "...הקלד בעברית"
            fonts.draw_text(self.display, placeholder, box_x + 8, box_y + 6, TEXT_MUTED, bg=SEARCH_BG)
        else:
            txt_with_cursor = disp_txt + "|"
            align = 'left' if self.kb.is_english else 'right'
            fonts.draw_text(self.display, txt_with_cursor, box_x + 8, box_y + 6, TEXT_DARK, bg=SEARCH_BG, max_width=box_w - 16, align=align)

    def draw_results_box(self):
        # Result area: Y: 62 to 134 (Height: 72px)
        rx, ry, rw, rh = 4, 62, 312, 72
        self.display.fill_rect(rx, ry, rw, rh, RESULT_BG)
        self.display.rect(rx, ry, rw, rh, KEY_BORDER)
        
        self.suggestion_rects = []
        
        if self.definition:
            # Translation title
            header_lbl = "תרגום:" if self.kb.is_english else "Translation:"
            fonts.draw_text(self.display, header_lbl, rx + 8, ry + 6, ACCENT_BLUE, bg=RESULT_BG)
            
            # Speak Button [🔊 הקרא]
            sx, sy, sw, sh = self.btn_speak["x"], self.btn_speak["y"], self.btn_speak["w"], self.btn_speak["h"]
            self.display.fill_rect(sx, sy, sw, sh, SPEAK_BG)
            self.display.rect(sx, sy, sw, sh, SPEAK_BORDER)
            fonts.draw_text(self.display, "הקרא" if self.kb.is_english else "SPEAK", sx + 18, sy + 3, WHITE, bg=SPEAK_BG)
            
            # Word wrap definition
            words = self.definition.split(' ')
            lines = []
            cur_line = ""
            for w in words:
                if len(cur_line) + len(w) + 1 <= 36:
                    cur_line = cur_line + " " + w if cur_line else w
                else:
                    lines.append(cur_line)
                    cur_line = w
            if cur_line:
                lines.append(cur_line)
                
            line_y = ry + 24
            for line in lines[:3]:
                fonts.draw_text(self.display, line, rx + 8, line_y, TEXT_DARK, bg=RESULT_BG, max_width=rw - 16)
                line_y += 15

        elif self.suggestions:
            # Suggestions for typo
            prompt = "התכוונת ל:" if self.kb.is_english else "Did you mean:"
            fonts.draw_text(self.display, prompt, rx + 8, ry + 6, RED, bg=RESULT_BG)
            
            s_x = rx + 8
            s_y = ry + 24
            for i, word in enumerate(self.suggestions[:4]):
                w_pixels = len(word) * fonts.WIDTH + 14
                if s_x + w_pixels > rx + rw - 8 and i > 0:
                    s_x = rx + 8
                    s_y += 22
                    if s_y + 20 > ry + rh:
                        break
                        
                # Draw pill button
                self.display.fill_rect(s_x, s_y, w_pixels, 18, SUGG_BG)
                self.display.rect(s_x, s_y, w_pixels, 18, SUGG_BORDER)
                fonts.draw_text(self.display, word, s_x + 7, s_y + 2, SUGG_TEXT, bg=SUGG_BG)
                
                self.suggestion_rects.append({
                    "word": word,
                    "x": s_x, "y": s_y, "w": w_pixels, "h": 18
                })
                s_x += w_pixels + 6
        else:
            # Friendly welcome / idle screen
            hint1 = "Bilingual Pocket Dictionary (RP2350)" if self.kb.is_english else "מילונית עברית-אנגלית (חטיבה ותיכון)"
            hint2 = "10,292 English  |  11,376 Hebrew"
            fonts.draw_text(self.display, hint1, rx + 8, ry + 20, ACCENT_BLUE, bg=RESULT_BG)
            fonts.draw_text(self.display, hint2, rx + 8, ry + 42, TEXT_MUTED, bg=RESULT_BG)

    def draw_ui(self):
        """Renders entire screen into FrameBuffer and flushes in one fast SPI transaction."""
        self.draw_top_bar()
        self.draw_search_box()
        self.draw_results_box()
        self.kb.draw(self.display, self.active_key)
        self.display.show()

    def run(self):
        print("Milonit UI loop running...")
        last_touch_time = 0
        
        while True:
            if self.needs_redraw:
                self.draw_ui()
                self.needs_redraw = False

            # Check capacitive touch
            pt = self.touch.get_touch()
            if pt is not None:
                tx, ty = pt
                now = time.ticks_ms()
                
                if time.ticks_diff(now, last_touch_time) > 170: # Debounce
                    last_touch_time = now
                    
                    # 1. Top Bar Clicks
                    if ty < 28:
                        if self.btn_mode["x"] <= tx <= self.btn_mode["x"] + self.btn_mode["w"]:
                            self.toggle_mode()
                        elif self.btn_vol["x"] <= tx <= self.btn_vol["x"] + self.btn_vol["w"]:
                            self.cycle_volume()
                        elif self.btn_clear["x"] <= tx <= self.btn_clear["x"] + self.btn_clear["w"]:
                            self.input_text = ""
                            self.definition = None
                            self.suggestions = []
                            self.suggestion_rects = []
                            self.status = "נוקה" if not self.kb.is_english else "Cleared"
                            self.audio.play_click()
                            self.needs_redraw = True
                            
                    # 2. Speak Button & Suggestion Pills Clicks
                    elif 62 <= ty <= 134:
                        # Check Speak button
                        if self.definition and (self.btn_speak["x"] <= tx <= self.btn_speak["x"] + self.btn_speak["w"]):
                            self.speak_current_word()
                        else:
                            for s_rect in self.suggestion_rects:
                                if s_rect["x"] <= tx <= s_rect["x"] + s_rect["w"] and s_rect["y"] <= ty <= s_rect["y"] + s_rect["h"]:
                                    self.audio.play_click()
                                    self.perform_search(s_rect["word"])
                                    break
                                    
                    # 3. Virtual Keyboard Clicks
                    elif ty >= 136:
                        key = self.kb.handle_touch(tx, ty)
                        if key:
                            self.audio.play_click()
                            self.active_key = key
                            self.kb.draw(self.display, self.active_key)
                            self.display.show()
                            
                            ktype = key["type"]
                            if ktype == "char":
                                self.input_text += key["value"]
                                self.needs_redraw = True
                            elif ktype == "backspace":
                                if len(self.input_text) > 0:
                                    self.input_text = self.input_text[:-1]
                                    self.needs_redraw = True
                            elif ktype == "lang":
                                self.toggle_mode()
                            elif ktype == "search":
                                self.perform_search()

                            time.sleep_ms(60)
                            self.active_key = None
                            self.needs_redraw = True
                            
            time.sleep_ms(15)

if __name__ in ("__main__", "main"):
    app = MilonitApp()
    app.run()
