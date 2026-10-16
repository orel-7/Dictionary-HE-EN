# Script to generate binary bitmap font for English and Hebrew characters
from PIL import Image, ImageDraw, ImageFont
import os

def generate_font():
    # Character set: ASCII 32..126 + Hebrew 0x05D0..0x05EA
    width = 8
    height = 14
    
    # Try to load Windows Tahoma or Arial
    font_path = "C:\\Windows\\Fonts\\tahoma.ttf"
    if not os.path.exists(font_path):
        font_path = "C:\\Windows\\Fonts\\arial.ttf"
    
    pil_font = ImageFont.truetype(font_path, 13)
    
    glyphs = {}
    
    # ASCII chars
    chars_to_render = [chr(c) for c in range(32, 127)]
    # Hebrew chars
    chars_to_render += [chr(c) for c in range(0x05D0, 0x05EB)]
    # Punctuation / extra
    chars_to_render += ['"', "'", '-', ',', '.', '?', '!', '/', ':', ';', '(', ')', '[', ']', '<', '>']
    
    for ch in chars_to_render:
        code = ord(ch)
        img = Image.new('1', (width, height), color=0)
        draw = ImageDraw.Draw(img)
        
        # Get bounding box or draw
        # Center horizontally if narrow
        draw.text((0, -2), ch, font=pil_font, fill=1)
        
        # Convert to 14 bytes (each byte is 8 horizontal pixels, MSB left)
        char_bytes = bytearray()
        for y in range(height):
            b = 0
            for x in range(width):
                pixel = img.getpixel((x, y))
                if pixel:
                    b |= (1 << (7 - x))
            char_bytes.append(b)
        glyphs[code] = bytes(char_bytes)

    # Export to MicroPython module font_data.py
    with open("font_data.py", "w", encoding="utf-8") as f:
        f.write("# Auto-generated 8x14 English & Hebrew Font for MicroPython\n")
        f.write("WIDTH = 8\n")
        f.write("HEIGHT = 14\n")
        f.write("GLYPHS = {\n")
        for code, b in sorted(glyphs.items()):
            hex_str = ", ".join(f"0x{byte:02x}" for byte in b)
            ch_repr = chr(code) if 32 <= code <= 126 or 0x05D0 <= code <= 0x05EA else f"U+{code:04X}"
            f.write(f"    0x{code:04x}: bytes([{hex_str}]), # {ch_repr}\n")
        f.write("}\n")
        
    print(f"Generated font with {len(glyphs)} glyphs.")

if __name__ == "__main__":
    generate_font()
