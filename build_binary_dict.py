# build_binary_dict.py
# Builds an ultra-fast, low-memory binary dictionary file (dict.bin) for MicroPython on Pico

import json
import struct

def build_binary_dict():
    with open("dict_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    en_to_he = data["en_to_he"]
    he_to_en = data["he_to_en"]
    
    # Sort keys alphabetically
    en_items = sorted(en_to_he.items(), key=lambda x: x[0])
    he_items = sorted(he_to_en.items(), key=lambda x: x[0])
    
    # Format:
    # Header:
    # 4 bytes: Magic B"PLMD" (Pico Language Milon Dictionary)
    # 4 bytes: EN items count (uint32)
    # 4 bytes: HE items count (uint32)
    # 4 bytes: Offset to EN table
    # 4 bytes: Offset to HE table
    #
    # Table entry:
    # Each entry:
    # 1 byte: word length (uint8)
    # N bytes: word UTF-8 bytes
    # 2 bytes: def length (uint16)
    # M bytes: definition UTF-8 bytes
    
    with open("dict.bin", "wb") as f:
        # Placeholder header (20 bytes)
        f.write(b"PLMD" + struct.pack("<IIII", 0, 0, 0, 0))
        
        en_offsets = []
        en_words = []
        en_table_start = f.tell()
        for word, definition in en_items:
            w_bytes = word.encode("utf-8")
            d_bytes = definition.encode("utf-8")
            en_offsets.append(f.tell())
            en_words.append(word)
            f.write(struct.pack("<B", len(w_bytes)) + w_bytes + struct.pack("<H", len(d_bytes)) + d_bytes)
            
        he_offsets = []
        he_words = []
        he_table_start = f.tell()
        for word, definition in he_items:
            w_bytes = word.encode("utf-8")
            d_bytes = definition.encode("utf-8")
            he_offsets.append(f.tell())
            he_words.append(word)
            f.write(struct.pack("<B", len(w_bytes)) + w_bytes + struct.pack("<H", len(d_bytes)) + d_bytes)
            
        # Index table for EN (array of uint32 file offsets)
        en_index_offset = f.tell()
        for off in en_offsets:
            f.write(struct.pack("<I", off))
            
        # Index table for HE (array of uint32 file offsets)
        he_index_offset = f.tell()
        for off in he_offsets:
            f.write(struct.pack("<I", off))
            
        # Seek back and write header
        f.seek(0)
        f.write(b"PLMD" + struct.pack("<IIII", len(en_items), len(he_items), en_index_offset, he_index_offset))
        
    print(f"Created dict.bin: {len(en_items)} EN items, {len(he_items)} HE items.")
    
    # Also write a lightweight search helper for typo detection
    # Storing words in a simple line-delimited index file
    with open("words_en.txt", "w", encoding="utf-8") as f:
        for w, _ in en_items:
            f.write(w + "\n")
            
    with open("words_he.txt", "w", encoding="utf-8") as f:
        for w, _ in he_items:
            f.write(w + "\n")

if __name__ == "__main__":
    build_binary_dict()
