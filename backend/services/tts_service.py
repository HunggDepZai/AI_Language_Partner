"""
TTS Service - Text-to-Speech cho tiếng Việt.
Hỗ trợ 3 engine:
  1. Edge-TTS (Microsoft) - Miễn phí, dễ cài, chất lượng tốt [MẶC ĐỊNH]
  2. VieNeu-TTS - Chạy local, voice cloning, CPU real-time
  3. VietTTS API - Server riêng, nhiều giọng đẹp
"""
import os
import io
import logging
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Voice mapping
EDGE_VOICES = {
    "female": "vi-VN-HoaiMyNeural",
    "male": "vi-VN-NamMinhNeural",
}


class TTSService:
    def __init__(self):
        self.engine = os.getenv("TTS_ENGINE", "edge")  # "edge", "vieneu", "viettts"
        self.rate = os.getenv("TTS_RATE", "+0%")
        self.pitch = os.getenv("TTS_PITCH", "+0Hz")
        self._vieneu_model = None
        logger.info(f"✅ TTS Service: {self.engine}")

    async def synthesize(self, text: str, voice: str = "female") -> Optional[bytes]:
        """Synthesize Vietnamese text to audio bytes (MP3)."""
        if not text or not text.strip():
            return None

        from utils.text_norm import normalize_vietnamese_text
        text = normalize_vietnamese_text(text)
        logger.debug(f"TTS Norm: {text}")

        try:
            if self.engine == "vieneu":
                return await self._synthesize_vieneu(text, voice)
            elif self.engine == "viettts":
                return await self._synthesize_viettts(text, voice)
            else:
                return await self._synthesize_edge(text, voice)
        except Exception as e:
            logger.error(f"TTS error ({self.engine}): {e}")
            # Fallback to Edge-TTS
            if self.engine != "edge":
                logger.info("Falling back to Edge-TTS...")
                return await self._synthesize_edge(text, voice)
            raise

    async def _synthesize_edge(self, text: str, voice: str) -> bytes:
        """Microsoft Edge-TTS - Free, high quality Vietnamese voices."""
        import edge_tts

        voice_name = EDGE_VOICES.get(voice, EDGE_VOICES["female"])

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate=self.rate,
            pitch=self.pitch,
        )

        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])

        return bytes(audio_data)

    async def _synthesize_vieneu(self, text: str, voice: str) -> bytes:
        """VieNeu-TTS - Local Vietnamese TTS with voice cloning."""
        import asyncio

        def _generate():
            if self._vieneu_model is None:
                from vieneu import Vieneu
                self._vieneu_model = Vieneu()

            audio = self._vieneu_model.infer(text=text)

            # Save to temp wav then convert
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                self._vieneu_model.save(audio, f.name)
                f.flush()
                with open(f.name, "rb") as wav_file:
                    wav_data = wav_file.read()
                os.unlink(f.name)
                return wav_data

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _generate)

    async def _synthesize_viettts(self, text: str, voice: str) -> bytes:
        """VietTTS API server - OpenAI compatible."""
        import httpx

        viettts_url = os.getenv("VIETTTS_URL", "http://localhost:8298")
        voice_id = "1" if voice == "female" else "2"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{viettts_url}/v1/audio/speech",
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": voice_id,
                    "response_format": "mp3",
                },
            )
            response.raise_for_status()
            return response.content
