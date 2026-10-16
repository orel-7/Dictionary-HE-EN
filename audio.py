# audio.py - High-Quality Audio & Phonetic Speech Synthesizer for RP2350-Touch-LCD-2.8
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
        self.i2s = None
        self.init_i2s()

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

    def set_volume(self, vol):
        self.volume = max(0, min(10, vol))

    def cycle_volume(self):
        """Cycles volume: 0 -> 3 -> 6 -> 8 -> 10 -> 0"""
        order = [0, 3, 6, 8, 10]
        if self.volume in order:
            idx = (order.index(self.volume) + 1) % len(order)
            self.volume = order[idx]
        else:
            self.volume = 7
        if self.volume > 0:
            self.play_tone(880, 0.08)
        return self.volume

    def play_samples(self, samples):
        """Plays mono int16 samples converted to stereo."""
        if not self.i2s or self.volume == 0:
            return

        vol_scale = self.volume / 10.0
        n_samples = len(samples)
        buf = bytearray(n_samples * 4) # 16-bit stereo = 4 bytes/sample
        
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

    def play_tone(self, freq, duration=0.1, amplitude=12000):
        if self.volume == 0:
            return
        n_samples = int(self.sample_rate * duration)
        samples = []
        for i in range(n_samples):
            # Smooth envelope at edges
            env = 1.0
            if i < 100: env = i / 100.0
            elif i > n_samples - 100: env = (n_samples - i) / 100.0
            val = int(math.sin(2 * math.pi * freq * i / self.sample_rate) * amplitude * env)
            samples.append(val)
        self.play_samples(samples)

    def play_click(self):
        """Short key-press click sound."""
        if self.volume == 0: return
        self.play_tone(1200, 0.015, amplitude=6000)

    def play_chime(self):
        """Success sound when word translation is found."""
        if self.volume == 0: return
        self.play_tone(523, 0.08, amplitude=10000) # C5
        time.sleep_ms(30)
        self.play_tone(659, 0.12, amplitude=12000) # E5

    def play_typo(self):
        """Tone when word is not found or has typos."""
        if self.volume == 0: return
        self.play_tone(330, 0.10, amplitude=8000)
        time.sleep_ms(30)
        self.play_tone(262, 0.14, amplitude=8000)

    # =========================================================================
    # Phonetic English Speech Synthesizer (Formant-Based Embedded TTS)
    # =========================================================================
    def _synthesize_vowel(self, f1, f2, duration=0.15, pitch=120):
        n = int(self.sample_rate * duration)
        samples = []
        pitch_period = int(self.sample_rate / pitch)
        
        for i in range(n):
            # Voice pulse modulation
            phase_pitch = (i % pitch_period) / pitch_period
            pulse = math.exp(-6 * phase_pitch)
            
            # Formants F1 and F2
            w1 = math.sin(2 * math.pi * f1 * i / self.sample_rate)
            w2 = 0.6 * math.sin(2 * math.pi * f2 * i / self.sample_rate)
            
            # Envelope
            env = math.sin(math.pi * i / n)
            val = int((w1 + w2) * pulse * 14000 * env)
            samples.append(val)
        return samples

    def _synthesize_fricative(self, duration=0.10, pitch=4000):
        n = int(self.sample_rate * duration)
        samples = []
        lfsr = 0xACE1
        for i in range(n):
            # 16-bit pseudo-random noise generator
            bit = ((lfsr >> 0) ^ (lfsr >> 2) ^ (lfsr >> 3) ^ (lfsr >> 5)) & 1
            lfsr = (lfsr >> 1) | (bit << 15)
            noise = (lfsr - 32768) / 32768.0
            
            env = math.sin(math.pi * i / n)
            val = int(noise * 8000 * env)
            samples.append(val)
        return samples

    def _synthesize_stop(self, voiced=False):
        # 20ms silence gap followed by 25ms burst
        silence = [0] * int(self.sample_rate * 0.02)
        burst_samples = []
        n_burst = int(self.sample_rate * 0.025)
        for i in range(n_burst):
            env = math.exp(-15 * i / n_burst)
            f = 400 if voiced else 2500
            w = math.sin(2 * math.pi * f * i / self.sample_rate)
            burst_samples.append(int(w * 12000 * env))
        return silence + burst_samples

    def speak_word(self, word):
        """Synthesizes speech pronunciation for an English word."""
        if not word or self.volume == 0:
            return

        w = word.strip().lower()
        full_samples = []
        i = 0
        
        # Phonetic formant mappings
        vowel_formants = {
            'a': (800, 1300),
            'e': (500, 1900),
            'i': (300, 2300),
            'o': (500, 900),
            'u': (350, 800),
            'y': (300, 2200),
        }
        
        while i < len(w):
            ch = w[i]
            # Check 2-letter digraphs
            pair = w[i:i+2]
            if pair in ('sh', 'ch'):
                full_samples.extend(self._synthesize_fricative(0.12, 3500))
                i += 2
                continue
            elif pair == 'th':
                full_samples.extend(self._synthesize_fricative(0.09, 5000))
                i += 2
                continue
            elif pair == 'ee' or pair == 'ea':
                full_samples.extend(self._synthesize_vowel(280, 2400, duration=0.18))
                i += 2
                continue
            elif pair == 'oo':
                full_samples.extend(self._synthesize_vowel(320, 800, duration=0.18))
                i += 2
                continue
            elif pair == 'ou' or pair == 'ow':
                full_samples.extend(self._synthesize_vowel(700, 1100, duration=0.10))
                full_samples.extend(self._synthesize_vowel(350, 800, duration=0.10))
                i += 2
                continue
            
            # 1-letter sounds
            if ch in vowel_formants:
                f1, f2 = vowel_formants[ch]
                full_samples.extend(self._synthesize_vowel(f1, f2, duration=0.14))
            elif ch in ('s', 'z', 'f', 'v'):
                full_samples.extend(self._synthesize_fricative(0.09))
            elif ch in ('p', 't', 'k'):
                full_samples.extend(self._synthesize_stop(voiced=False))
            elif ch in ('b', 'd', 'g'):
                full_samples.extend(self._synthesize_stop(voiced=True))
            elif ch in ('m', 'n'):
                full_samples.extend(self._synthesize_vowel(250, 1100, duration=0.10, pitch=100))
            elif ch in ('l', 'r'):
                full_samples.extend(self._synthesize_vowel(380, 1300, duration=0.11))
            elif ch == ' ':
                full_samples.extend([0] * int(self.sample_rate * 0.10))
                
            i += 1

        if full_samples:
            self.play_samples(full_samples)
