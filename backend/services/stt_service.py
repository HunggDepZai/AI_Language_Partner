"""
Speech-to-Text Service using OpenAI Whisper or Groq Whisper API.
Optimized for Vietnamese language.
"""
import io
import os
import logging
import tempfile

logger = logging.getLogger(__name__)


class STTService:
    def __init__(self):
        self.provider = os.getenv("STT_PROVIDER", "openai")  # "openai" or "groq"
        self.model = os.getenv("STT_MODEL", "whisper-1")
        logger.info(f"✅ STT Service: {self.provider} / {self.model}")

    async def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        """Transcribe audio bytes to Vietnamese text."""
        if self.provider == "groq":
            return await self._transcribe_groq(audio_bytes, language)
        return await self._transcribe_openai(audio_bytes, language)

    async def _transcribe_openai(self, audio_bytes: bytes, language: str) -> str:
        """Use OpenAI Whisper API."""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # Write to temp WAV file
            wav_bytes = self._pcm_to_wav(audio_bytes)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                f.flush()
                temp_path = f.name

            with open(temp_path, "rb") as audio_file:
                response = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="text",
                    prompt="Đây là đoạn hội thoại tiếng Việt.",
                )

            os.unlink(temp_path)
            return response.strip()

        except Exception as e:
            logger.error(f"OpenAI STT error: {e}")
            raise

    async def _transcribe_groq(self, audio_bytes: bytes, language: str) -> str:
        """Use Groq Whisper API (faster, free tier)."""
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

            wav_bytes = self._pcm_to_wav(audio_bytes)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                f.flush()
                temp_path = f.name

            with open(temp_path, "rb") as audio_file:
                response = await client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=audio_file,
                    language=language,
                    response_format="text",
                    prompt="Đây là đoạn hội thoại tiếng Việt.",
                )

            os.unlink(temp_path)
            return response.strip()

        except Exception as e:
            logger.error(f"Groq STT error: {e}")
            # Fallback to OpenAI
            logger.info("Falling back to OpenAI Whisper...")
            return await self._transcribe_openai(audio_bytes, language)

    @staticmethod
    def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
        """Convert raw PCM bytes to WAV format."""
        import struct
        data_size = len(pcm_bytes)
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + data_size,
            b'WAVE',
            b'fmt ',
            16,  # chunk size
            1,   # PCM format
            channels,
            sample_rate,
            sample_rate * channels * sample_width,
            channels * sample_width,
            sample_width * 8,
            b'data',
            data_size,
        )
        return header + pcm_bytes
