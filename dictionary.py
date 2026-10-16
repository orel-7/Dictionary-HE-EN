# dictionary.py - Ultra-fast bilingual dictionary with Typo / Fuzzy search for MicroPython
import struct
import os

def levenshtein_dist(s1, s2, max_dist=3):
    """Calculates Levenshtein distance with early exit threshold."""
    l1, l2 = len(s1), len(s2)
    if abs(l1 - l2) > max_dist:
        return max_dist + 1
        
    if l1 > l2:
        s1, s2 = s2, s1
        l1, l2 = l2, l1

    current = list(range(l1 + 1))
    for i in range(1, l2 + 1):
        prev = current
        current = [i] + [0] * l1
        min_in_row = i
        for j in range(1, l1 + 1):
            add = prev[j] + 1
            delete = current[j - 1] + 1
            change = prev[j - 1]
            if s1[j - 1] != s2[i - 1]:
                change += 1
            current[j] = min(add, delete, change)
            if current[j] < min_in_row:
                min_in_row = current[j]
        if min_in_row > max_dist:
            return max_dist + 1
            
    return current[l1]

class BilingualDictionary:
    def __init__(self, dict_path=None):
        if dict_path is None:
            # Check SD card first, then internal flash
            try:
                os.stat("/sd/dict.bin")
                self.dict_path = "/sd/dict.bin"
            except Exception:
                self.dict_path = "dict.bin"
        else:
            self.dict_path = dict_path
            
        self.file = None
        self.en_count = 0
        self.he_count = 0
        self.en_index_offset = 0
        self.he_index_offset = 0
        self.open_dict()

    def open_dict(self):
        try:
            self.file = open(self.dict_path, "rb")
            magic = self.file.read(4)
            if magic != b"PLMD":
                print("Invalid dictionary format!")
                return False
            hdr = self.file.read(16)
            self.en_count, self.he_count, self.en_index_offset, self.he_index_offset = struct.unpack("<IIII", hdr)
            return True
        except Exception as e:
            print("Failed to open dict:", e)
            return False

    def _read_entry(self, entry_offset):
        self.file.seek(entry_offset)
        w_len = struct.unpack("<B", self.file.read(1))[0]
        word = self.file.read(w_len).decode("utf-8")
        d_len = struct.unpack("<H", self.file.read(2))[0]
        definition = self.file.read(d_len).decode("utf-8")
        return word, definition

    def _get_entry_offset(self, index, is_english=True):
        idx_base = self.en_index_offset if is_english else self.he_index_offset
        self.file.seek(idx_base + index * 4)
        offset = struct.unpack("<I", self.file.read(4))[0]
        return offset

    def lookup(self, query, is_english=True):
        """
        Binary search for exact match.
        Returns (definition, None) if found.
        If not found, returns (None, [suggestions]) with closest typo corrections!
        """
        if not self.file:
            return None, ["Dict not loaded"]
            
        clean_query = query.strip().lower() if is_english else query.strip()
        if not clean_query:
            return None, []

        count = self.en_count if is_english else self.he_count
        low = 0
        high = count - 1
        found_def = None

        # Binary search
        while low <= high:
            mid = (low + high) // 2
            offset = self._get_entry_offset(mid, is_english)
            word, definition = self._read_entry(offset)
            word_comp = word.lower() if is_english else word

            if word_comp == clean_query:
                return definition, []
            elif word_comp < clean_query:
                low = mid + 1
            else:
                high = mid - 1

        # Not found -> find typo suggestions / fuzzy matches
        suggestions = self.get_fuzzy_suggestions(clean_query, is_english, limit=4)
        return None, suggestions

    def _find_prefix_range(self, prefix, is_english=True):
        """Finds the [start_idx, end_idx] range for a given prefix using binary search."""
        count = self.en_count if is_english else self.he_count
        if count == 0 or not prefix:
            return 0, count

        # 1. Lower bound (first word >= prefix)
        low, high = 0, count - 1
        start_idx = count
        while low <= high:
            mid = (low + high) // 2
            offset = self._get_entry_offset(mid, is_english)
            word, _ = self._read_entry(offset)
            w_comp = word.lower() if is_english else word
            if w_comp >= prefix:
                start_idx = mid
                high = mid - 1
            else:
                low = mid + 1

        # 2. Upper bound
        prefix_next = prefix[:-1] + chr(ord(prefix[-1]) + 1)
        low, high = start_idx, count - 1
        end_idx = count
        while low <= high:
            mid = (low + high) // 2
            offset = self._get_entry_offset(mid, is_english)
            word, _ = self._read_entry(offset)
            w_comp = word.lower() if is_english else word
            if w_comp >= prefix_next:
                end_idx = mid
                high = mid - 1
            else:
                low = mid + 1

        return start_idx, end_idx

    def get_fuzzy_suggestions(self, query, is_english=True, limit=4):
        """Finds closest matching words in ~50ms using binary prefix range scoping."""
        count = self.en_count if is_english else self.he_count
        if count == 0 or not query:
            return []

        candidates = []
        q_len = len(query)

        # Pass 1: Try 2-letter prefix range (ultra-fast, ~50-150 words)
        start_idx, end_idx = 0, count
        if len(query) >= 2:
            start_idx, end_idx = self._find_prefix_range(query[:2], is_english)
            
        # If 2-letter range is too small, fall back to 1-letter range (~600 words)
        if (end_idx - start_idx) < 3 and len(query) >= 1:
            start_idx, end_idx = self._find_prefix_range(query[:1], is_english)

        # Clamp search window to max 600 words for guaranteed <80ms response
        if end_idx - start_idx > 600:
            end_idx = start_idx + 600

        for i in range(start_idx, end_idx):
            offset = self._get_entry_offset(i, is_english)
            self.file.seek(offset)
            w_len = struct.unpack("<B", self.file.read(1))[0]
            
            # Skip if word length is too different
            if abs(w_len - q_len) > 3:
                continue
                
            word = self.file.read(w_len).decode("utf-8")
            word_comp = word.lower() if is_english else word
            
            dist = levenshtein_dist(query, word_comp, max_dist=3)
            if dist <= 3:
                score = dist
                if word_comp.startswith(query[:2]):
                    score -= 0.5
                candidates.append((score, word))
                # Early exit if we already have strong matches
                if len(candidates) >= limit * 2:
                    break

        candidates.sort(key=lambda x: x[0])
        res = []
        for _, w in candidates:
            if w not in res:
                res.append(w)
            if len(res) >= limit:
                break
        return res
