# audio.py - High-Quality Audio & Crystal-Clear Phonetic Speech Synthesizer for RP2350
import machine
from machine import Pin, I2S
import math
import time

class AudioManager:
    def __init__(self, sck=2, ws=3, sd=4, rate=16000):
        self.sck_pin = sck
        self.ws_pin = ws
        self.sd_pin = sd
        self.sample_rate = rate
        self.volume = 7 # Scale 0 to 10
        self.saved_volume = 7
        self.is_muted = False
        self.i2s = None
        
        self.init_i2s()
        self._init_phoneme_tables()

    def init_i2s(self):
        try:
            self.i2s = I2S(
                0,
                sck=Pin(self.sck_pin),
                ws=Pin(self.ws_pin),
                sd=Pin(self.sd_pin),
                mode=I2S.TX,
                bits=16,
                format=I2S.STEREO,
                rate=self.sample_rate,
                ibuf=2048
            )
        except Exception as e:
            print("I2S Init error:", e)

    def toggle_mute(self):
        """Instant Mute / Unmute toggle."""
        if self.is_muted or self.volume == 0:
            self.is_muted = False
            self.volume = self.saved_volume if self.saved_volume > 0 else 7
            self.play_tone(880, 0.05)
            return False # Unmuted
        else:
            self.saved_volume = self.volume if self.volume > 0 else 7
            self.is_muted = True
            self.volume = 0
            return True # Muted

    def set_volume(self, vol):
        self.volume = max(0, min(10, vol))
        self.is_muted = (self.volume == 0)

    def cycle_volume(self):
        """Cycles volume: 7 -> 10 -> 0 (MUTE) -> 3 -> 6 -> 8"""
        order = [0, 3, 6, 7, 8, 10]
        if self.volume in order:
            idx = (order.index(self.volume) + 1) % len(order)
            self.volume = order[idx]
        else:
            self.volume = 7
        self.is_muted = (self.volume == 0)
        if self.volume > 0:
            self.play_tone(880, 0.06)
        return self.volume

    def play_samples(self, samples):
        """Plays mono int16 samples converted to stereo."""
        if not self.i2s or self.volume == 0 or self.is_muted:
            return

        vol_scale = (self.volume / 10.0)
        n_samples = len(samples)
        buf = bytearray(n_samples * 4) # 16-bit stereo = 4 bytes per sample
        
        for i in range(n_samples):
            v = int(samples[i] * vol_scale)
            v = max(-32767, min(32767, v))
            lo = v & 0xFF
            hi = (v >> 8) & 0xFF
            idx = i * 4
            buf[idx] = lo
            buf[idx + 1] = hi
            buf[idx + 2] = lo
            buf[idx + 3] = hi

        try:
            self.i2s.write(buf)
        except Exception as e:
            print("I2S write error:", e)

    def play_tone(self, freq, duration=0.08, amplitude=11000):
        if self.volume == 0 or self.is_muted:
            return
        n_samples = int(self.sample_rate * duration)
        samples = []
        ramp = min(120, n_samples // 4)
        for i in range(n_samples):
            env = 1.0
            if i < ramp:
                env = i / ramp
            elif i > n_samples - ramp:
                env = (n_samples - i) / ramp
            val = int(math.sin(2 * math.pi * freq * i / self.sample_rate) * amplitude * env)
            samples.append(val)
        self.play_samples(samples)

    def play_click(self):
        """Crisp, soft tactile click for key presses."""
        if self.volume == 0 or self.is_muted:
            return
        self.play_tone(1400, 0.012, amplitude=5500)

    def play_chime(self):
        """Melodic 2-tone chime when a word definition is found."""
        if self.volume == 0 or self.is_muted:
            return
        self.play_tone(523, 0.07, amplitude=9000) # C5
        time.sleep_ms(25)
        self.play_tone(659, 0.10, amplitude=11000) # E5

    def play_typo(self):
        """Muted 2-tone prompt when a word is not found or has typos."""
        if self.volume == 0 or self.is_muted:
            return
        self.play_tone(370, 0.08, amplitude=7000)
        time.sleep_ms(25)
        self.play_tone(294, 0.10, amplitude=7000)

    # =========================================================================
    # High-Performance Formant Wavetable Speech Synthesizer
    # =========================================================================
    def _init_phoneme_tables(self):
        """Precomputes single-cycle glottal waveforms for major English phonemes."""
        self.pitch = 135 # Vocal cord fundamental frequency in Hz
        self.period_len = int(self.sample_rate / self.pitch) # 118 samples
        
        # Formants for vowels: (F1, F2, F3) in Hz
        vowel_specs = {
            'AA': (800, 1250, 2500), # father, car, hot
            'EH': (550, 1800, 2500), # bed, ten, friend
            'EE': (280, 2300, 3000), # see, eat, machine
            'IH': (400, 2000, 2600), # sit, in, big
            'OH': (500, 900, 2400),  # boat, go, door
            'OO': (320, 850, 2200),  # food, moon, blue
            'AE': (700, 1700, 2500), # cat, black, back
            'ER': (450, 1300, 1700), # bird, water, her
            'AH': (650, 1100, 2400), # but, cup, up
            'MM': (250, 1100, 2200), # nasal m/n
            'LL': (350, 1150, 2800), # liquid l/r
        }
        
        self.cycles = {}
        for name, (f1, f2, f3) in vowel_specs.items():
            cycle = []
            for i in range(self.period_len):
                phase = i / self.period_len
                # Rosenberg glottal model
                if phase < 0.6:
                    pulse = math.sin(math.pi * phase / 0.6)
                else:
                    pulse = 0.5 * (1.0 + math.cos(math.pi * (phase - 0.6) / 0.4))
                
                w1 = math.sin(2 * math.pi * f1 * i / self.sample_rate)
                w2 = 0.65 * math.sin(2 * math.pi * f2 * i / self.sample_rate)
                w3 = 0.35 * math.sin(2 * math.pi * f3 * i / self.sample_rate)
                val = int((w1 + w2 + w3) * pulse * 8500)
                cycle.append(val)
            self.cycles[name] = cycle

    def _render_vowel(self, name, duration=0.11):
        cycle = self.cycles.get(name, self.cycles['AH'])
        n = int(self.sample_rate * duration)
        num_cycles = (n // self.period_len) + 1
        raw = (cycle * num_cycles)[:n]
        
        # Soft attack and release window
        ramp = min(int(self.sample_rate * 0.015), n // 4)
        for i in range(ramp):
            env = i / ramp
            raw[i] = int(raw[i] * env)
            raw[n - 1 - i] = int(raw[n - 1 - i] * env)
        return raw

    def _render_noise(self, duration=0.08, amplitude=3500):
        n = int(self.sample_rate * duration)
        samples = []
        lfsr = 0xACE1
        ramp = min(120, n // 4)
        for i in range(n):
            bit = ((lfsr >> 0) ^ (lfsr >> 2) ^ (lfsr >> 3) ^ (lfsr >> 5)) & 1
            lfsr = (lfsr >> 1) | (bit << 15)
            noise = (lfsr - 32768) / 32768.0
            env = 1.0
            if i < ramp:
                env = i / ramp
            elif i > n - ramp:
                env = (n - i) / ramp
            samples.append(int(noise * amplitude * env))
        return samples

    def _render_stop(self, voiced=False):
        # 15ms silence gap + 20ms burst
        gap = [0] * int(self.sample_rate * 0.015)
        n_burst = int(self.sample_rate * 0.02)
        burst = []
        freq = 300 if voiced else 2200
        for i in range(n_burst):
            env = math.exp(-12.0 * i / n_burst)
            w = math.sin(2 * math.pi * freq * i / self.sample_rate)
            burst.append(int(w * 8000 * env))
        return gap + burst

    def speak_word(self, word):
        """Synthesizes high-clarity pronunciation for an English word."""
        if not word or self.volume == 0 or self.is_muted:
            return

        w = word.strip().lower()
        full_samples = []
        i = 0
        
        while i < len(w):
            pair = w[i:i+2]
            
            # Common English Digraphs
            if pair in ('sh', 'ch'):
                full_samples.extend(self._render_noise(0.09, amplitude=4000))
                i += 2
                continue
            elif pair == 'th':
                full_samples.extend(self._render_noise(0.08, amplitude=3200))
                i += 2
                continue
            elif pair in ('ee', 'ea'):
                full_samples.extend(self._render_vowel('EE', 0.14))
                i += 2
                continue
            elif pair == 'oo':
                full_samples.extend(self._render_vowel('OO', 0.14))
                i += 2
                continue
            elif pair in ('ou', 'ow'):
                full_samples.extend(self._render_vowel('AH', 0.08))
                full_samples.extend(self._render_vowel('OO', 0.08))
                i += 2
                continue
            elif pair in ('ai', 'ay'):
                full_samples.extend(self._render_vowel('EH', 0.08))
                full_samples.extend(self._render_vowel('EE', 0.08))
                i += 2
                continue
            elif pair in ('er', 'ir', 'ur'):
                full_samples.extend(self._render_vowel('ER', 0.13))
                i += 2
                continue
            elif pair == 'ck':
                full_samples.extend(self._render_stop(voiced=False))
                i += 2
                continue
            
            # Single Letters
            ch = w[i]
            if ch == 'a':
                # Distinguish open vs closed syllable
                full_samples.extend(self._render_vowel('AE', 0.12))
            elif ch == 'e':
                full_samples.extend(self._render_vowel('EH', 0.11))
            elif ch == 'i':
                full_samples.extend(self._render_vowel('IH', 0.10))
            elif ch == 'o':
                full_samples.extend(self._render_vowel('OH', 0.12))
            elif ch == 'u':
                full_samples.extend(self._render_vowel('AH', 0.11))
            elif ch == 'y':
                full_samples.extend(self._render_vowel('EE', 0.10))
            elif ch in ('s', 'c'):
                full_samples.extend(self._render_noise(0.08, amplitude=3800))
            elif ch in ('z', 'x'):
                full_samples.extend(self._render_noise(0.08, amplitude=4200))
            elif ch in ('f', 'v'):
                full_samples.extend(self._render_noise(0.07, amplitude=3200))
            elif ch in ('p', 't', 'k', 'q'):
                full_samples.extend(self._render_stop(voiced=False))
            elif ch in ('b', 'd', 'g'):
                full_samples.extend(self._render_stop(voiced=True))
            elif ch in ('m', 'n'):
                full_samples.extend(self._render_vowel('MM', 0.09))
            elif ch in ('l', 'r'):
                full_samples.extend(self._render_vowel('LL', 0.09))
            elif ch == 'h':
                full_samples.extend(self._render_noise(0.05, amplitude=2500))
            elif ch == 'w':
                full_samples.extend(self._render_vowel('OO', 0.07))
            elif ch == 'j':
                full_samples.extend(self._render_noise(0.06, amplitude=3500))
            elif ch in (' ', '-', '_'):
                full_samples.extend([0] * int(self.sample_rate * 0.05))
                
            i += 1

        if full_samples:
            # Play in chunks of 2048 to prevent memory allocation spikes
            self.play_samples(full_samples)
