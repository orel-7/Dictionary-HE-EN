# main.py - Bilingual Pocket Dictionary (Milonit) for RP2350-Touch-LCD-2.8
import time
import os
import gc
import machine
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
        
        # 1. Standard Factory Frequency 150 MHz for maximum battery life and hardware longevity
        try:
            machine.freq(150_000_000)
            print("CPU Frequency set to factory standard 150 MHz.")
        except Exception as e:
            print("Frequency setting notice:", e)

        # 2. Power enable for RP2350 (BAT_EN)
        try:
            self.bat_en = Pin(26, Pin.OUT, value=1)
        except Exception:
            pass

        # 3. Initialize Display (High-Speed SPI 62.5MHz with 153KB FrameBuffer)
        self.display = ST7789(width=320, height=240)
        
        # 4. Mount MicroSD Card if inserted
        self.mount_sd_card()
        
        # 5. Initialize CST328 Capacitive Touch Controller
        self.touch = CST328(width=320, height=240, rotation=1)
        
        # 6. Initialize I2S Audio & Speech Synthesizer
        self.audio = AudioManager(sck=2, ws=3, sd=4, rate=16000)
        
        # 7. Initialize Binary Indexed Bilingual Dictionary
        self.dict = BilingualDictionary()
        print(f"Loaded Dictionary: {self.dict.en_count} EN, {self.dict.he_count} HE words.")
        
        # 8. Initialize Virtual Keyboard
        self.kb = VirtualKeyboard(y_start=138, height=100)
        
        # 9. App State
        self.input_text = ""
        self.definition = None
        self.suggestions = []
        self.suggestion_rects = []
        self.status = f"מוכן ({self.dict.en_count + self.dict.he_count})"
        self.needs_redraw = True
        
        # Touch state machine (immune to double typing / bouncing)
        self.touch_down = False
        self.active_key = None
        self.last_tap_time = 0
        
        # Search History (stack of previous searches for Back button)
        self.history = []
        
        # Interactive UI Button Rectangles (X, Y, W, H)
        self.btn_mode  = {"x": 4,   "y": 3, "w": 74, "h": 22} # [EN/עב]
        self.btn_back  = {"x": 82,  "y": 3, "w": 28, "h": 22} # [ ◄ ] Back arrow
        self.btn_sound = {"x": 218, "y": 3, "w": 52, "h": 22} # [🔊 ON] / [🔇 OFF]
        self.btn_clear = {"x": 274, "y": 3, "w": 42, "h": 22} # [CLR]
        self.btn_speak = {"x": 228, "y": 66, "w": 82, "h": 20} # [🔊 הקרא]
        
        # Initial greeting sound
        self.audio.play_tone(600, 0.05)

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
        except Exception:
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

    def toggle_sound(self):
        is_muted = self.audio.toggle_mute()
        self.status = "השתק" if is_muted else f"שמע: {self.audio.volume}"
        self.draw_top_bar()

    def go_back(self):
        """Navigates back to the previously searched word in history."""
        if len(self.history) > 1:
            self.history.pop() # Remove current word
            prev_word, prev_is_en, prev_defn, prev_suggs = self.history[-1]
            if self.kb.is_english != prev_is_en:
                self.kb.toggle_language()
            self.input_text = prev_word
            self.definition = prev_defn
            self.suggestions = prev_suggs
            self.status = "חזרה אחורה" if not self.kb.is_english else "Back"
            self.audio.play_click()
            self.needs_redraw = True
        elif len(self.history) == 1:
            self.history.clear()
            self.input_text = ""
            self.definition = None
            self.suggestions = []
            self.status = "תחילת היסטוריה"
            self.audio.play_click()
            self.needs_redraw = True

    def speak_current_word(self):
        """Speaks English word (either query or translation)."""
        target = ""
        if self.kb.is_english:
            target = self.input_text.strip()
        elif self.definition:
            target = self.definition.split(',')[0].split(';')[0].strip()
        
        if target:
            # Highlight speak button visually (Active blue state)
            sx, sy, sw, sh = self.btn_speak["x"], self.btn_speak["y"], self.btn_speak["w"], self.btn_speak["h"]
            self.display.fill_rect(sx, sy, sw, sh, ACCENT_BLUE)
            self.display.rect(sx, sy, sw, sh, WHITE)
            fonts.draw_text(self.display, "משמיע..." if self.kb.is_english else "PLAY...", sx + 6, sy + 3, WHITE, bg=ACCENT_BLUE)
            self.display.flush_rect(sx, sy, sw, sh)
            
            try:
                self.audio.speak_word(target)
            except Exception as e:
                print("Speech playback notice:", e)
            
            # Restore normal green button
            self.display.fill_rect(sx, sy, sw, sh, SPEAK_BG)
            self.display.rect(sx, sy, sw, sh, SPEAK_BORDER)
            fonts.draw_text(self.display, "הקרא" if self.kb.is_english else "SPEAK", sx + 18, sy + 3, WHITE, bg=SPEAK_BG)
            self.display.flush_rect(sx, sy, sw, sh)

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
        self.draw_top_bar()
        self.draw_search_box()

        defn, suggs = self.dict.lookup(query, is_english=self.kb.is_english)
        self.definition = defn
        self.suggestions = suggs
        self.suggestion_rects = []
        
        if defn:
            self.status = "נמצא!" if not self.kb.is_english else "Found!"
            # Add to search history stack (max 10 items)
            if not self.history or self.history[-1][0].lower() != query.lower():
                self.history.append((query, self.kb.is_english, defn, suggs))
                if len(self.history) > 10:
                    self.history.pop(0)
            self.audio.play_chime()
        elif suggs:
            self.status = "שגיאת כתיב?" if not self.kb.is_english else "Typo? Suggestions:"
            self.audio.play_typo()
        else:
            self.status = "לא נמצא" if not self.kb.is_english else "Not found"
            self.audio.play_typo()
            
        self.needs_redraw = True
        gc.collect()

    def draw_top_bar(self):
        # Header bar background
        self.display.fill_rect(0, 0, 320, 28, HEADER_BG)
        
        # 1. Mode button [EN/עב]
        mx, my, mw, mh = self.btn_mode["x"], self.btn_mode["y"], self.btn_mode["w"], self.btn_mode["h"]
        self.display.fill_rect(mx, my, mw, mh, ACCENT_BLUE)
        self.display.rect(mx, my, mw, mh, WHITE)
        mode_label = "EN->עב" if self.kb.is_english else "עב->EN"
        fonts.draw_text(self.display, mode_label, mx + 5, my + 4, WHITE, bg=ACCENT_BLUE)
        
        # 2. Back button [ ◄ ]
        bx, by, bw, bh = self.btn_back["x"], self.btn_back["y"], self.btn_back["w"], self.btn_back["h"]
        has_history = len(self.history) > 1
        b_bg = ACCENT_BLUE if has_history else rgb(51, 65, 85)
        b_fg = WHITE if has_history else GRAY
        self.display.fill_rect(bx, by, bw, bh, b_bg)
        self.display.rect(bx, by, bw, bh, WHITE if has_history else rgb(71, 85, 105))
        fonts.draw_text(self.display, "<", bx + 10, by + 4, b_fg, bg=b_bg)
        
        # 3. Status text
        fonts.draw_text(self.display, self.status, 116, 7, LIGHT_GRAY, bg=HEADER_BG, max_width=98)
        
        # 4. Sound Mute / Unmute Button [🔊 ON] / [🔇 OFF]
        vx, vy, vw, vh = self.btn_sound["x"], self.btn_sound["y"], self.btn_sound["w"], self.btn_sound["h"]
        is_muted = self.audio.is_muted or self.audio.volume == 0
        s_bg = rgb(185, 28, 28) if is_muted else rgb(22, 101, 52)
        s_lbl = "MUTE" if is_muted else f"ON:{self.audio.volume}"
        self.display.fill_rect(vx, vy, vw, vh, s_bg)
        self.display.rect(vx, vy, vw, vh, WHITE)
        fonts.draw_text(self.display, s_lbl, vx + 5, vy + 4, WHITE, bg=s_bg)
        
        # 5. Clear button [CLR]
        cx, cy, cw, ch = self.btn_clear["x"], self.btn_clear["y"], self.btn_clear["w"], self.btn_clear["h"]
        self.display.fill_rect(cx, cy, cw, ch, rgb(71, 85, 105))
        self.display.rect(cx, cy, cw, ch, WHITE)
        fonts.draw_text(self.display, "CLR", cx + 7, cy + 4, WHITE, bg=rgb(71, 85, 105))
        
        self.display.flush_rect(0, 0, 320, 28)

    def draw_search_box(self):
        """Renders search input box and flushes in 7ms for ultra-responsive typing."""
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
            
        self.display.flush_rect(box_x, box_y, box_w, box_h)

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
            # Welcome banner
            hint1 = "Bilingual Pocket Dictionary (RP2350)" if self.kb.is_english else "מילונית עברית-אנגלית (חטיבה ותיכון)"
            hint2 = "10,292 English  |  11,376 Hebrew"
            fonts.draw_text(self.display, hint1, rx + 8, ry + 20, ACCENT_BLUE, bg=RESULT_BG)
            fonts.draw_text(self.display, hint2, rx + 8, ry + 42, TEXT_MUTED, bg=RESULT_BG)

        self.display.flush_rect(rx, ry, rw, rh)

    def draw_ui(self):
        """Renders entire screen into FrameBuffer and flushes in one fast transaction."""
        self.draw_top_bar()
        self.draw_search_box()
        self.draw_results_box()
        self.kb.draw(self.display, self.active_key)
        self.display.show()

    def handle_tap(self, tx, ty):
        """Processes a single touch-down tap event (strictly once per touch)."""
        # 1. Top Bar Clicks
        if ty < 28:
            if self.btn_mode["x"] <= tx <= self.btn_mode["x"] + self.btn_mode["w"]:
                self.toggle_mode()
            elif self.btn_back["x"] <= tx <= self.btn_back["x"] + self.btn_back["w"]:
                self.go_back()
            elif self.btn_sound["x"] <= tx <= self.btn_sound["x"] + self.btn_sound["w"]:
                self.toggle_sound()
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
                self.active_key = key
                # Instant visual press highlight on the single key (0.5ms)
                self.kb.draw_key(self.display, key, is_pressed=True, flush=True)
                self.audio.play_click()

                ktype = key["type"]
                if ktype == "char":
                    self.input_text += key["value"]
                    # Ultra-fast partial refresh of search box (7ms)
                    self.draw_search_box()
                elif ktype == "backspace":
                    if len(self.input_text) > 0:
                        self.input_text = self.input_text[:-1]
                        self.draw_search_box()
                elif ktype == "lang":
                    self.toggle_mode()
                elif ktype == "search":
                    self.perform_search()

    def run(self):
        print("Milonit UI loop running with touch state machine...")
        
        while True:
            if self.needs_redraw:
                self.draw_ui()
                self.needs_redraw = False

            # Touch event polling
            pt = self.touch.get_touch()
            now = time.ticks_ms()

            if pt is not None:
                tx, ty = pt
                if not self.touch_down:
                    # Fresh touch down edge: trigger ONCE with comfortable 150ms debounce
                    if time.ticks_diff(now, self.last_tap_time) > 150:
                        self.touch_down = True
                        self.last_tap_time = now
                        self.handle_tap(tx, ty)
            else:
                # Finger released (touch up)
                if self.touch_down:
                    self.touch_down = False
                    if self.active_key:
                        # Restore normal key visual
                        self.kb.draw_key(self.display, self.active_key, is_pressed=False, flush=True)
                        self.active_key = None

            time.sleep_ms(15)

if __name__ in ("__main__", "main"):
    app = MilonitApp()
    app.run()
