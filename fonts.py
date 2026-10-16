# fonts.py - Ultra-Fast ST7789 Direct SPI Font Renderer for Hebrew and English
import font_data

WIDTH = font_data.WIDTH
HEIGHT = font_data.HEIGHT
GLYPHS = font_data.GLYPHS

# Pre-allocated 224 byte buffer for 8x14 character glyphs (8 * 14 * 2 = 224 bytes)
_char_buf = bytearray(WIDTH * HEIGHT * 2)

def is_hebrew(ch):
    return 0x05D0 <= ord(ch) <= 0x05EA

def has_hebrew(text):
    for ch in text:
        if is_hebrew(ch):
            return True
    return False

def prepare_rtl_text(text):
    """
    Reverses Hebrew segments so that standard left-to-right drawing renders them properly.
    """
    if not has_hebrew(text):
        return text
        
    chars = list(text)
    i = 0
    while i < len(chars):
        if is_hebrew(chars[i]):
            j = i
            while j < len(chars) and (is_hebrew(chars[j]) or chars[j] in " -'\""):
                j += 1
            chars[i:j] = chars[i:j][::-1]
            i = j
        else:
            i += 1
    return "".join(chars)

def draw_char(display, ch, x, y, color, bg=None):
    """
    Draws a single character directly into the display FrameBuffer.
    """
    if x >= display.width or y >= display.height or x + WIDTH <= 0 or y + HEIGHT <= 0:
        return WIDTH
        
    code = ord(ch)
    glyph = GLYPHS.get(code)
    if not glyph:
        glyph = GLYPHS.get(32) # Space fallback
        if not glyph:
            return WIDTH

    fg_lo = color & 0xFF
    fg_hi = (color >> 8) & 0xFF
    has_bg = (bg is not None and bg >= 0)
    if has_bg:
        bg_lo = bg & 0xFF
        bg_hi = (bg >> 8) & 0xFF

    buf = getattr(display, 'buffer', None)
    w = display.width
    h = display.height

    if buf is not None:
        for row in range(HEIGHT):
            py = y + row
            if 0 <= py < h:
                byte = glyph[row]
                row_offset = (py * w + x) * 2
                for col in range(WIDTH):
                    px = x + col
                    if 0 <= px < w:
                        idx = row_offset + col * 2
                        if (byte >> (7 - col)) & 1:
                            buf[idx] = fg_lo
                            buf[idx + 1] = fg_hi
                        elif has_bg:
                            buf[idx] = bg_lo
                            buf[idx + 1] = bg_hi
    else:
        for row in range(HEIGHT):
            py = y + row
            if 0 <= py < h:
                byte = glyph[row]
                for col in range(WIDTH):
                    px = x + col
                    if 0 <= px < w:
                        if (byte >> (7 - col)) & 1:
                            display.pixel(px, py, color)
                        elif has_bg:
                            display.pixel(px, py, bg)
    return WIDTH

def draw_text(display, text, x, y, color, bg=None, max_width=320, align='left'):
    """
    Draws a text string with RTL support and alignment directly to display.
    """
    if has_hebrew(text):
        text = prepare_rtl_text(text)
        
    text_width = len(text) * WIDTH
    if align == 'center':
        x = x + (max_width - text_width) // 2
    elif align == 'right':
        x = x + max_width - text_width

    cur_x = x
    for ch in text:
        if cur_x + WIDTH > x + max_width:
            break
        draw_char(display, ch, cur_x, y, color, bg)
        cur_x += WIDTH
    return cur_x
