# build_super_dictionary.py
# Downloads and compiles an enormous high-quality bidirectional English <-> Hebrew dictionary
# Combines:
# 1. Ministry of Education Junior High & High School vocabulary (Bands I, II, III Bagrut)
# 2. Curated modern conversational & academic English-Hebrew vocabulary
# 3. Comprehensive Wiktionary (Kaikki) English-Hebrew vocabulary pairs

import json
import os
import re
import urllib.request
import struct
from build_dictionary import load_base_vocabulary

def clean_gloss(gloss):
    # Remove parenthetical notes like (biology) or (dated)
    g = re.sub(r'\(.*?\)', '', gloss)
    g = re.sub(r'\[.*?\]', '', g)
    g = g.replace('"', '').replace("'", "").strip()
    # If it starts with "to ", keep it clean
    return g

def build_super_dict():
    print("1. Loading curated Junior High & High School baseline...")
    base_vocab = load_base_vocabulary()
    print(f"Base vocabulary: {len(base_vocab)} words.")

    en_to_he = {}
    he_to_en = {}

    # Seed base
    for en, he in base_vocab.items():
        en_clean = en.strip().lower()
        he_clean = he.strip()
        en_to_he[en_clean] = he_clean
        for part in he_clean.replace('/', ',').split(','):
            p = part.strip()
            if p and len(p) >= 2:
                if p not in he_to_en: he_to_en[p] = []
                if en_clean not in he_to_en[p]: he_to_en[p].append(en_clean)

    print(f"2. Downloading and extracting Kaikki Wiktionary Hebrew database (~59MB)...")
    url = 'https://kaikki.org/dictionary/Hebrew/words/kaikki.org-dictionary-Hebrew-words.jsonl'
    
    cache_file = "kaikki_hebrew.jsonl"
    if not os.path.exists(cache_file):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp, open(cache_file, 'wb') as out_f:
            total_read = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk: break
                out_f.write(chunk)
                total_read += len(chunk)
                print(f"  Downloaded {total_read // (1024*1024)} MB...", end='\r')
        print(f"\nDownload completed: {os.path.getsize(cache_file)} bytes.")
    else:
        print("Using existing cached", cache_file)

    print("3. Parsing and filtering entries...")
    added_pairs = 0
    with open(cache_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
                
            he_word = entry.get('word', '').strip()
            # Must be Hebrew letters (no nikud/vocalizations to keep typing clean)
            # Remove Hebrew vowels/cantillation (0x0591 to 0x05C7)
            he_clean = re.sub(r'[\u0591-\u05C7]', '', he_word).strip()
            
            # Check if all chars are hebrew / space / hyphen
            if not all(0x05D0 <= ord(c) <= 0x05EA or c in ' -"' for c in he_clean):
                continue
            if len(he_clean) < 2 or len(he_clean) > 25:
                continue

            senses = entry.get('senses', [])
            all_defs = []
            for s in senses:
                for g in s.get('glosses', []):
                    cg = clean_gloss(g)
                    # Filter out non-dictionary descriptions
                    if len(cg) > 1 and len(cg) < 50 and not any(skip in cg.lower() for skip in ['given name', 'surname', 'acronym', 'spelling of']):
                        # Take simple headwords
                        first_few = [w.strip().lower() for w in cg.split(',') if w.strip()]
                        for item in first_few[:2]:
                            # only basic ascii english
                            if re.match(r'^[a-z]+(\s[a-z]+)?$', item) and len(item) >= 2:
                                all_defs.append(item)

            if not all_defs:
                continue

            # Add to mappings
            primary_en = all_defs[0]
            if primary_en not in en_to_he:
                en_to_he[primary_en] = he_clean
                added_pairs += 1
            else:
                # Append if short
                existing = en_to_he[primary_en]
                if he_clean not in existing and len(existing) < 60:
                    en_to_he[primary_en] = existing + ", " + he_clean

            if he_clean not in he_to_en:
                he_to_en[he_clean] = []
            for d in all_defs[:3]:
                if d not in he_to_en[he_clean]:
                    he_to_en[he_clean].append(d)

    print(f"Added {added_pairs} new word pairs from Wiktionary.")

    # Flatten he_to_en
    he_to_en_flat = {k: ", ".join(v[:4]) for k, v in he_to_en.items() if v}

    print(f"Total English words: {len(en_to_he)}")
    print(f"Total Hebrew words: {len(he_to_en_flat)}")

    # Save to dict_data.json
    data = {
        "en_to_he": en_to_he,
        "he_to_en": he_to_en_flat
    }
    with open("dict_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("Saved dict_data.json.")

    # Build binary dict
    print("4. Compiling into indexed binary file dict.bin...")
    en_items = sorted(en_to_he.items(), key=lambda x: x[0])
    he_items = sorted(he_to_en_flat.items(), key=lambda x: x[0])

    with open("dict.bin", "wb") as f:
        # Placeholder header (20 bytes)
        f.write(b"PLMD" + struct.pack("<IIII", 0, 0, 0, 0))
        
        en_offsets = []
        for word, definition in en_items:
            w_bytes = word.encode("utf-8")
            d_bytes = definition.encode("utf-8")
            en_offsets.append(f.tell())
            f.write(struct.pack("<B", len(w_bytes)) + w_bytes + struct.pack("<H", len(d_bytes)) + d_bytes)
            
        he_offsets = []
        for word, definition in he_items:
            w_bytes = word.encode("utf-8")
            d_bytes = definition.encode("utf-8")
            he_offsets.append(f.tell())
            f.write(struct.pack("<B", len(w_bytes)) + w_bytes + struct.pack("<H", len(d_bytes)) + d_bytes)
            
        en_index_offset = f.tell()
        for off in en_offsets:
            f.write(struct.pack("<I", off))
            
        he_index_offset = f.tell()
        for off in he_offsets:
            f.write(struct.pack("<I", off))
            
        f.seek(0)
        f.write(b"PLMD" + struct.pack("<IIII", len(en_items), len(he_items), en_index_offset, he_index_offset))

    size_mb = os.path.getsize("dict.bin") / (1024 * 1024)
    print(f"Built dict.bin: {len(en_items)} EN words, {len(he_items)} HE words. File size: {size_mb:.2f} MB")

if __name__ == "__main__":
    build_super_dict()
