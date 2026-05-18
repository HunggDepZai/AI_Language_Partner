"""
Voice Activity Detection (VAD) — Full-Duplex Turn Detection
Dùng Silero VAD (nếu có torch) hoặc Energy+ZCR fallback.

Fix so với version cũ:
  - Silero: dùng đủ 512 sample chuẩn + accumulate window
  - Energy fallback: adaptive threshold + Zero Crossing Rate
  - TurnDetector: pre-roll buffer đúng, silence timeout dùng time thực tế
  - Config hợp lý hơn: silence 1.2s, min_speech 400ms
"""
import numpy as np
import logging
import os
import time
import collections
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512          # Silero yêu cầu đúng 512 samples mỗi lần gọi


class TurnState(Enum):
    IDLE         = "idle"
    LISTENING    = "listening"
    SPEECH       = "speech"
    SPEECH_ENDED = "speech_ended"


# ─────────────────────────────────────────────────────────────────────────────
class VADService:
    """
    VAD với 2 backend:
      1. Silero VAD (torch) — chính xác, ~1ms/frame trên CPU
      2. Energy + ZCR       — fallback khi không có torch
    """

    def __init__(self):
        self.threshold        = float(os.getenv("VAD_THRESHOLD", "0.45"))
        # Tuned for ChatGPT-Voice / Gemini-Live feel: end the turn quickly when
        # the user pauses so the assistant can reply almost immediately. 600ms
        # is short enough to feel snappy but long enough to ride over natural
        # in-sentence pauses (~250-400ms in Vietnamese conversational speech).
        self.silence_ms       = int(os.getenv("VAD_SILENCE_DURATION", "600"))    # ms im lặng → kết thúc lượt
        self.min_speech_ms    = int(os.getenv("VAD_MIN_SPEECH", "300"))          # ms tối thiểu để tính là speech
        self.speech_pad_ms    = int(os.getenv("VAD_SPEECH_PAD_MS", "300"))       # ms padding trước speech (pre-roll)
        self.speech_start_frames = int(os.getenv("VAD_SPEECH_START_FRAMES", "2"))
        # 4 frames @ ~256ms/frame ≈ 1s — kept above silence_ms so the time-based
        # check (silence_ms) is what normally triggers end-of-turn.
        self.silence_end_frames  = int(os.getenv("VAD_SILENCE_END_FRAMES", "4"))

        self.model = None
        self._sample_buf = np.array([], dtype=np.float32)  # accumulate cho Silero
        self._load_model()

    def _load_model(self):
        try:
            import torch
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
                verbose=False,
            )
            self.model = model
            logger.info("✅ Silero VAD loaded")
        except Exception as e:
            logger.warning(f"Silero VAD không load được: {e} → dùng Energy+ZCR fallback")
            self.model = None

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        if self.model is not None:
            return self._silero_detect(audio_chunk)
        return self._energy_zcr_detect(audio_chunk)

    def _silero_detect(self, audio_chunk: np.ndarray) -> bool:
        """
        Silero yêu cầu đúng 512 samples (16kHz) mỗi lần gọi.
        Accumulate sample rồi gọi theo window 512.
        """
        try:
            import torch
            self._sample_buf = np.concatenate([self._sample_buf, audio_chunk])
            result = False
            while len(self._sample_buf) >= CHUNK_SAMPLES:
                window = self._sample_buf[:CHUNK_SAMPLES]
                self._sample_buf = self._sample_buf[CHUNK_SAMPLES:]
                tensor = torch.from_numpy(window).float()
                conf = self.model(tensor, SAMPLE_RATE).item()
                if conf > self.threshold:
                    result = True   # bất kỳ window nào có speech → True
            return result
        except Exception as e:
            logger.debug(f"Silero error: {e}")
            return self._energy_zcr_detect(audio_chunk)

    def _energy_zcr_detect(self, audio_chunk: np.ndarray) -> bool:
        """
        Kết hợp RMS energy + Zero Crossing Rate để phân biệt speech/noise.
        Speech: energy cao + ZCR vừa phải (không quá cao như noise).
        """
        if len(audio_chunk) < 160:
            return False

        # RMS energy
        rms = float(np.sqrt(np.mean(audio_chunk ** 2)))

        # Zero Crossing Rate (tỷ lệ lần đổi dấu)
        signs = np.sign(audio_chunk)
        signs[signs == 0] = 1
        zcr = float(np.mean(np.abs(np.diff(signs))) / 2)

        # Speech: rms > ngưỡng VÀ zcr trong khoảng hợp lý (0.05–0.45)
        is_speech = (rms > 0.015) and (0.04 < zcr < 0.5)
        return is_speech

    def reset(self):
        self._sample_buf = np.array([], dtype=np.float32)
        if self.model is not None:
            try:
                self.model.reset_states()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
class TurnDetector:
    """
    Full-duplex turn detector.

    Flow:
      LISTENING → (speech_start_frames liên tiếp) → SPEECH
      SPEECH    → (silence_end_frames liên tiếp VÀ thời gian thực ≥ silence_ms) → speech_end event
                                              ↓
                                          LISTENING (reset buffer)

    Pre-roll: giữ ~300ms audio trước khi speech bắt đầu để Whisper có context.
    """

    def __init__(self, vad: VADService):
        self.vad   = vad
        self.state = TurnState.IDLE

        self._consecutive_speech  = 0
        self._consecutive_silence = 0
        self._speech_start_time: Optional[float] = None
        self._last_speech_time:  Optional[float] = None

        # Pre-roll buffer: deque giới hạn kích thước (~speech_pad_ms)
        pre_roll_bytes = int(vad.speech_pad_ms / 1000 * SAMPLE_RATE * 2)  # 16-bit
        self._pre_roll: collections.deque = collections.deque(maxlen=pre_roll_bytes)
        self._audio_buffer = bytearray()

        # Lấy config từ VAD
        self._speech_start_thr = vad.speech_start_frames
        self._silence_end_thr  = vad.silence_end_frames
        self._min_speech_s     = vad.min_speech_ms / 1000.0
        self._silence_s        = vad.silence_ms / 1000.0

    # ── Public ────────────────────────────────────────────────────────────────

    def reset(self):
        self.state = TurnState.IDLE
        self._consecutive_speech  = 0
        self._consecutive_silence = 0
        self._speech_start_time   = None
        self._last_speech_time    = None
        self._audio_buffer        = bytearray()
        self._pre_roll.clear()
        self.vad.reset()

    def start_listening(self):
        self.state = TurnState.LISTENING
        self._consecutive_speech  = 0
        self._consecutive_silence = 0
        self._speech_start_time   = None
        self._last_speech_time    = None
        self._audio_buffer        = bytearray()
        self._pre_roll.clear()
        self.vad.reset()
        logger.debug("TurnDetector: LISTENING")

    def process_audio(self, pcm_bytes: bytes) -> dict:
        """
        Nhận PCM 16-bit mono chunk, trả về dict:
          is_speech: bool
          event:     'speech_start' | 'speech_end' | None
          audio:     bytes (khi speech_end) | None
        """
        if self.state == TurnState.IDLE:
            return {"is_speech": False, "event": None, "audio": None}

        audio_np  = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        is_speech = self.vad.is_speech(audio_np)
        now       = time.monotonic()
        event     = None
        audio_out = None

        if is_speech:
            self._consecutive_speech  += 1
            self._consecutive_silence  = 0
            self._last_speech_time     = now

            if self.state == TurnState.LISTENING:
                # Gom vào pre-roll khi chưa chắc là speech
                for b in pcm_bytes:
                    self._pre_roll.append(b)

                if self._consecutive_speech >= self._speech_start_thr:
                    # Xác nhận speech — lấy pre-roll làm đầu buffer
                    self.state = TurnState.SPEECH
                    self._speech_start_time = now
                    self._audio_buffer = bytearray(self._pre_roll)
                    self._audio_buffer.extend(pcm_bytes)
                    self._pre_roll.clear()
                    event = "speech_start"
                    logger.debug("TurnDetector: SPEECH started")

            elif self.state == TurnState.SPEECH:
                self._audio_buffer.extend(pcm_bytes)

            elif self.state == TurnState.SPEECH_ENDED:
                # User bắt đầu nói lại trong khi đang chờ confirm end
                self.state = TurnState.SPEECH
                self._audio_buffer.extend(pcm_bytes)

        else:
            self._consecutive_silence += 1
            self._consecutive_speech   = 0

            if self.state == TurnState.LISTENING:
                # Cập nhật pre-roll với silence (để capture context trước speech)
                for b in pcm_bytes:
                    self._pre_roll.append(b)

            elif self.state == TurnState.SPEECH:
                self._audio_buffer.extend(pcm_bytes)

                # Kiểm tra kết thúc lượt: dùng CẢ HAI điều kiện
                silence_elapsed = (now - self._last_speech_time) if self._last_speech_time else 0
                frames_ok = self._consecutive_silence >= self._silence_end_thr
                time_ok   = silence_elapsed >= self._silence_s

                if frames_ok or time_ok:
                    speech_duration = (now - self._speech_start_time) if self._speech_start_time else 0
                    logger.debug(
                        f"TurnDetector: speech_end check — duration={speech_duration:.2f}s "
                        f"silence={silence_elapsed:.2f}s frames={self._consecutive_silence}"
                    )

                    if speech_duration >= self._min_speech_s:
                        event     = "speech_end"
                        audio_out = bytes(self._audio_buffer)
                        logger.info(
                            f"✅ Turn end: {speech_duration:.2f}s speech, "
                            f"{len(audio_out)} bytes → STT"
                        )
                    else:
                        logger.debug(f"Turn too short ({speech_duration:.2f}s < {self._min_speech_s}s), discard")

                    # Reset về LISTENING dù có đủ dài hay không
                    self._audio_buffer = bytearray()
                    self.state = TurnState.LISTENING
                    self._pre_roll.clear()
                    self.vad.reset()

            elif self.state == TurnState.SPEECH_ENDED:
                pass

        return {"is_speech": is_speech, "event": event, "audio": audio_out}

    def get_buffered_audio(self) -> bytes:
        return bytes(self._audio_buffer)