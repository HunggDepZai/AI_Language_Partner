"""
Voice Activity Detection (VAD) for Full-Duplex Conversation.
Uses Silero VAD to detect speech start/end in real-time.
Supports: turn detection, silence timeout, barge-in.
"""
import numpy as np
import logging
import os
import time
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


class TurnState(Enum):
    IDLE = "idle"                  # Not listening
    LISTENING = "listening"        # Mic open, waiting for speech
    SPEECH = "speech"              # User is speaking
    SPEECH_ENDED = "speech_ended"  # User stopped, waiting to confirm end


class VADService:
    def __init__(self):
        self.model = None
        self.threshold = float(os.getenv("VAD_THRESHOLD", "0.5"))
        # How long silence before we consider the turn ended (ms)
        self.silence_duration_ms = int(os.getenv("VAD_SILENCE_DURATION", "800"))
        # Minimum speech duration to count as valid (ms)
        self.min_speech_ms = int(os.getenv("VAD_MIN_SPEECH", "250"))
        # How many consecutive speech frames to confirm speech start
        self.speech_start_frames = int(os.getenv("VAD_SPEECH_START_FRAMES", "2"))
        # How many consecutive silence frames to confirm speech end
        self.silence_end_frames = int(os.getenv("VAD_SILENCE_END_FRAMES", "6"))

        self._load_model()

    def _load_model(self):
        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self.model = model
            logger.info("Silero VAD loaded for full-duplex mode")
        except Exception as e:
            logger.warning(f"Silero VAD failed to load: {e}. Using energy-based VAD fallback.")
            self.model = None

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Check if audio chunk contains speech."""
        if self.model is not None:
            return self._silero_detect(audio_chunk)
        return self._energy_detect(audio_chunk)

    def _silero_detect(self, audio_chunk: np.ndarray) -> bool:
        """Use Silero VAD model."""
        try:
            import torch
            if len(audio_chunk) < 512:
                return False
            tensor = torch.from_numpy(audio_chunk[-512:]).float()
            confidence = self.model(tensor, SAMPLE_RATE).item()
            return confidence > self.threshold
        except Exception:
            return self._energy_detect(audio_chunk)

    def _energy_detect(self, audio_chunk: np.ndarray) -> bool:
        """Fallback: simple energy-based VAD."""
        if len(audio_chunk) < 160:
            return False
        energy = np.sqrt(np.mean(audio_chunk ** 2))
        return energy > 0.01  # Adjust threshold as needed

    def reset(self):
        """Reset VAD model state."""
        if self.model is not None:
            try:
                self.model.reset_states()
            except Exception:
                pass


class TurnDetector:
    """
    Real-time turn detector for full-duplex conversation.
    Tracks speech state and fires callbacks on turn boundaries.
    """

    def __init__(self, vad: VADService):
        self.vad = vad
        self.state = TurnState.IDLE
        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._speech_start_time: Optional[float] = None
        self._last_speech_time: Optional[float] = None
        self._audio_buffer = bytearray()

        # Config from VAD
        self._speech_start_threshold = vad.speech_start_frames
        self._silence_end_threshold = vad.silence_end_frames
        self._min_speech_s = vad.min_speech_ms / 1000.0
        self._silence_timeout_s = vad.silence_duration_ms / 1000.0

    def reset(self):
        """Reset turn detector state."""
        self.state = TurnState.IDLE
        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._speech_start_time = None
        self._last_speech_time = None
        self._audio_buffer = bytearray()
        self.vad.reset()

    def start_listening(self):
        """Start listening for speech."""
        self.state = TurnState.LISTENING
        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._speech_start_time = None
        self._last_speech_time = None
        self._audio_buffer = bytearray()
        self.vad.reset()

    def process_audio(self, pcm_bytes: bytes) -> dict:
        """
        Process an audio chunk and return turn detection events.

        Returns dict with:
          - 'is_speech': bool - is current chunk speech
          - 'event': str or None - 'speech_start', 'speech_end', None
          - 'audio': bytes or None - accumulated audio when speech_end
        """
        if self.state == TurnState.IDLE:
            return {"is_speech": False, "event": None, "audio": None}

        # Convert PCM to float for VAD
        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        is_speech = self.vad.is_speech(audio_np)
        now = time.time()

        event = None
        audio_out = None

        if is_speech:
            self._consecutive_speech += 1
            self._consecutive_silence = 0
            self._last_speech_time = now

            if self.state == TurnState.LISTENING:
                if self._consecutive_speech >= self._speech_start_threshold:
                    # Speech detected!
                    self.state = TurnState.SPEECH
                    self._speech_start_time = now
                    event = "speech_start"
                    # Include buffered audio
                    self._audio_buffer.extend(pcm_bytes)
                else:
                    # Buffer audio in case speech is starting
                    self._audio_buffer.extend(pcm_bytes)

            elif self.state == TurnState.SPEECH:
                self._audio_buffer.extend(pcm_bytes)

            elif self.state == TurnState.SPEECH_ENDED:
                # User started speaking again
                self.state = TurnState.SPEECH
                self._audio_buffer.extend(pcm_bytes)

        else:
            self._consecutive_silence += 1
            self._consecutive_speech = 0

            if self.state == TurnState.LISTENING:
                # Keep a small rolling buffer for pre-speech audio
                self._audio_buffer.extend(pcm_bytes)
                # Limit pre-buffer to ~0.5s
                max_pre_buffer = SAMPLE_RATE * 2  # 0.5s at 16bit mono
                if len(self._audio_buffer) > max_pre_buffer:
                    self._audio_buffer = self._audio_buffer[-max_pre_buffer:]

            elif self.state == TurnState.SPEECH:
                self._audio_buffer.extend(pcm_bytes)
                if self._consecutive_silence >= self._silence_end_threshold:
                    self.state = TurnState.SPEECH_ENDED
                    # Check if speech was long enough
                    if self._speech_start_time and (now - self._speech_start_time) >= self._min_speech_s:
                        event = "speech_end"
                        audio_out = bytes(self._audio_buffer)
                        self._audio_buffer = bytearray()
                        self.state = TurnState.LISTENING
                        self.vad.reset()
                    else:
                        # Too short, ignore and keep listening
                        self.state = TurnState.LISTENING
                        self._audio_buffer = bytearray()
                        self.vad.reset()

            elif self.state == TurnState.SPEECH_ENDED:
                # Already ended, stay in ended state
                pass

        return {"is_speech": is_speech, "event": event, "audio": audio_out}

    def get_buffered_audio(self) -> bytes:
        """Get current buffered audio."""
        return bytes(self._audio_buffer)