"""
Speech-to-Text Service — Nhận dạng giọng nói tiếng Việt
Backend: OpenAI Whisper API / Groq Whisper API
Fix: PCM→WAV header đúng, validate audio, cleanup temp, noise gate.
"""
import os
import logging
import struct
import tempfile
import numpy as np

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000            # Backend luôn nhận PCM 16-bit mono 16kHz
MIN_AUDIO_DURATION_S = 0.3     # Bỏ audio ngắn hơn 0.3s
MAX_AUDIO_DURATION_S = 30.0    # Cắt audio dài quá 30s
SILENCE_RMS_THRESHOLD = 0.005  # Ngưỡng RMS dưới đây coi như silence (float32)
MIN_SPEECH_RATIO = 0.05        # Ít nhất 5% frames là speech mới gửi STT

# Prompt giúp Whisper nhận dạng tiếng Việt tốt hơn
VIETNAMESE_PROMPT = (
    "Xin chào, đây là đoạn hội thoại tiếng Việt. "
    "Hà Nội, Hồ Chí Minh, Đà Nẵng, Hội An, Huế, Sapa, Phú Quốc, Nha Trang."
)


class STTService:
    def __init__(self):
        self.provider = os.getenv("STT_PROVIDER", "openai").lower()
        self.model = os.getenv("STT_MODEL", "whisper-1")
        logger.info(f"✅ STT Service: provider={self.provider} model={self.model}")

    async def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        """
        Transcribe raw PCM 16-bit mono 16kHz bytes thành text.
        Tự validate, lọc silence, chuyển WAV đúng rồi mới gửi API.
        """
        # ── Validate audio cơ bản ──
        if not audio_bytes or len(audio_bytes) < 100:
            logger.warning("STT: audio rỗng hoặc quá ngắn, bỏ qua")
            return ""

        # ── Chuyển PCM sang float32 để phân tích ──
        pcm_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = pcm_int16.astype(np.float32) / 32768.0

        # ── Kiểm tra thời lượng ──
        duration_s = len(audio_float) / SAMPLE_RATE
        if duration_s < MIN_AUDIO_DURATION_S:
            logger.warning(f"STT: audio quá ngắn ({duration_s:.2f}s < {MIN_AUDIO_DURATION_S}s), bỏ qua")
            return ""

        # Cắt nếu quá dài
        if duration_s > MAX_AUDIO_DURATION_S:
            logger.info(f"STT: cắt audio từ {duration_s:.1f}s xuống {MAX_AUDIO_DURATION_S}s")
            max_samples = int(MAX_AUDIO_DURATION_S * SAMPLE_RATE)
            pcm_int16 = pcm_int16[:max_samples]
            audio_float = audio_float[:max_samples]
            audio_bytes = pcm_int16.tobytes()

        # ── Noise gate: kiểm tra có speech thực sự không ──
        rms = float(np.sqrt(np.mean(audio_float ** 2)))
        if rms < SILENCE_RMS_THRESHOLD:
            logger.debug(f"STT: audio toàn silence (RMS={rms:.5f}), bỏ qua")
            return ""

        # Kiểm tra tỷ lệ frames có speech (đơn giản: amplitude > threshold)
        speech_frames = np.sum(np.abs(audio_float) > 0.01)
        speech_ratio = speech_frames / len(audio_float)
        if speech_ratio < MIN_SPEECH_RATIO:
            logger.debug(f"STT: speech ratio quá thấp ({speech_ratio:.3f}), bỏ qua")
            return ""

        logger.info(f"STT: processing {duration_s:.2f}s audio (RMS={rms:.4f}, speech={speech_ratio:.2%})")

        # ── Chuyển PCM → WAV ──
        wav_bytes = self._pcm_to_wav(audio_bytes)

        # ── Gọi API ──
        if self.provider == "groq":
            return await self._transcribe_groq(wav_bytes, language)
        return await self._transcribe_openai(wav_bytes, language)

    async def _transcribe_openai(self, wav_bytes: bytes, language: str) -> str:
        """OpenAI Whisper API — whisper-1."""
        temp_path = None
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # Ghi WAV ra temp file (API cần file object)
            temp_path = self._write_temp_wav(wav_bytes)

            with open(temp_path, "rb") as audio_file:
                response = await client.audio.transcriptions.create(
                    model=self.model,        # dùng model từ env, không hardcode
                    file=audio_file,
                    language=language,
                    response_format="text",
                    prompt=VIETNAMESE_PROMPT,
                )

            text = response.strip() if isinstance(response, str) else str(response).strip()
            logger.info(f"STT OpenAI result: '{text[:80]}'")
            return text

        except Exception as e:
            logger.error(f"OpenAI STT error: {e}")
            raise
        finally:
            self._cleanup_temp(temp_path)

    async def _transcribe_groq(self, wav_bytes: bytes, language: str) -> str:
        """Groq Whisper API — whisper-large-v3 (nhanh hơn, free tier)."""
        temp_path = None
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

            temp_path = self._write_temp_wav(wav_bytes)

            with open(temp_path, "rb") as audio_file:
                response = await client.audio.transcriptions.create(
                    model=self.model if "whisper" in self.model else "whisper-large-v3",
                    file=audio_file,
                    language=language,
                    response_format="text",
                    prompt=VIETNAMESE_PROMPT,
                )

            text = response.strip() if isinstance(response, str) else str(response).strip()
            logger.info(f"STT Groq result: '{text[:80]}'")
            return text

        except Exception as e:
            logger.error(f"Groq STT error: {e}")
            # Fallback sang OpenAI nếu Groq lỗi
            logger.info("STT: Groq lỗi → fallback OpenAI Whisper")
            wav_bytes_for_fallback = wav_bytes  # đã có sẵn wav
            temp_fb = None
            try:
                from openai import AsyncOpenAI
                client_fb = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                temp_fb = self._write_temp_wav(wav_bytes_for_fallback)
                with open(temp_fb, "rb") as af:
                    resp = await client_fb.audio.transcriptions.create(
                        model="whisper-1",
                        file=af,
                        language=language,
                        response_format="text",
                        prompt=VIETNAMESE_PROMPT,
                    )
                return resp.strip() if isinstance(resp, str) else str(resp).strip()
            except Exception as e2:
                logger.error(f"Fallback OpenAI STT cũng lỗi: {e2}")
                raise e  # raise lỗi gốc
            finally:
                self._cleanup_temp(temp_fb)
        finally:
            self._cleanup_temp(temp_path)

    # ── PCM → WAV ─────────────────────────────────────────────────────────────

    @staticmethod
    def _pcm_to_wav(
        pcm_bytes: bytes,
        sample_rate: int = SAMPLE_RATE,
        channels: int = 1,
        sample_width: int = 2   # 16-bit = 2 bytes
    ) -> bytes:
        """
        Chuyển raw PCM bytes thành WAV.
        Header WAV phải CHÍNH XÁC:
          - RIFF header
          - fmt chunk (PCM, mono, 16kHz, 16-bit)
          - data chunk
        """
        data_size = len(pcm_bytes)
        byte_rate = sample_rate * channels * sample_width
        block_align = channels * sample_width
        bits_per_sample = sample_width * 8

        # Build header thủ công để tránh sai byte order
        header = bytearray()
        header += b'RIFF'
        header += struct.pack('<I', 36 + data_size)      # ChunkSize
        header += b'WAVE'
        header += b'fmt '
        header += struct.pack('<I', 16)                   # Subchunk1Size (PCM)
        header += struct.pack('<H', 1)                    # AudioFormat (1 = PCM)
        header += struct.pack('<H', channels)             # NumChannels
        header += struct.pack('<I', sample_rate)          # SampleRate
        header += struct.pack('<I', byte_rate)            # ByteRate
        header += struct.pack('<H', block_align)          # BlockAlign
        header += struct.pack('<H', bits_per_sample)      # BitsPerSample
        header += b'data'
        header += struct.pack('<I', data_size)            # Subchunk2Size

        return bytes(header) + pcm_bytes

    @staticmethod
    def _write_temp_wav(wav_bytes: bytes) -> str:
        """Ghi WAV bytes ra temp file và trả về path."""
        f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            f.write(wav_bytes)
            f.flush()
            return f.name
        finally:
            f.close()

    @staticmethod
    def _cleanup_temp(path):
        """Xóa temp file an toàn."""
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
