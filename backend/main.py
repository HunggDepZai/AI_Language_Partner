"""
Vietnamese Voice AI Assistant - Full-Duplex Backend Server
Pipeline: Continuous Audio → VAD Turn Detection → STT → LLM → TTS → Audio
Supports: barge-in, auto turn detection, no push-to-talk needed.
"""
import asyncio
import base64
import json
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from services.stt_service import STTService
from services.llm_service import LLMService
from services.tts_service import TTSService
from services.vad_service import VADService, TurnDetector
from services.rag_service import RAGService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Globals ──
vad_service: Optional[VADService] = None
stt_service: Optional[STTService] = None
llm_service: Optional[LLMService] = None
tts_service: Optional[TTSService] = None
rag_service: Optional[RAGService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all services on startup."""
    global vad_service, stt_service, llm_service, tts_service, rag_service
    logger.info("Khoi dong Vietnamese Voice AI - Full-Duplex Mode...")

    vad_service = VADService()
    stt_service = STTService()
    llm_service = LLMService()
    tts_service = TTSService()
    rag_service = RAGService()
    await rag_service.initialize()

    logger.info("Tat ca services da san sang!")
    yield
    logger.info("Dang tat server...")


app = FastAPI(title="Vietnamese Voice AI - Full Duplex", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConversationSession:
    """Manages a full-duplex voice conversation session."""

    def __init__(self):
        self.conversation_history: list[dict] = []
        self.voice = os.getenv("DEFAULT_VOICE", "female")
        self.is_ai_speaking = False
        self.cancelled = False
        self.is_conversation_active = False
        self.max_history = int(os.getenv("MAX_CONVERSATION_HISTORY", "20"))
        self.turn_detector: Optional[TurnDetector] = None
        self.pipeline_task: Optional[asyncio.Task] = None
        # Lock to prevent overlapping pipeline runs
        self.pipeline_lock = asyncio.Lock()

    def add_message(self, role: str, content: str):
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]


@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "Vietnamese Voice AI Full-Duplex dang hoat dong"}


@app.get("/api/health/rag")
async def rag_health():
    ready = bool(rag_service and rag_service.is_ready)
    return {
        "status": "ok" if ready else "not_ready",
        "rag_ready": ready
    }


@app.get("/api/voices")
async def get_voices():
    return {
        "voices": [
            {"id": "female", "name": "Hoai My (Nu)", "code": "vi-VN-HoaiMyNeural"},
            {"id": "male", "name": "Nam Minh (Nam)", "code": "vi-VN-NamMinhNeural"},
        ]
    }


@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    await websocket.accept()
    session = ConversationSession()
    logger.info("Client ket noi WebSocket")

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == "config":
                session.voice = msg.get("voice", session.voice)
                await websocket.send_json({
                    "type": "config_ok",
                    "voice": session.voice,
                    "mode": "full_duplex"
                })

            elif msg_type == "start_conversation":
                # User toggled conversation ON — start full-duplex
                await start_conversation(websocket, session)

            elif msg_type == "stop_conversation":
                # User toggled conversation OFF
                await stop_conversation(websocket, session)

            elif msg_type == "audio_chunk":
                # Continuous audio from client
                if session.is_conversation_active and session.turn_detector:
                    chunk = base64.b64decode(msg["data"])
                    await handle_audio_chunk(websocket, session, chunk)

            elif msg_type == "interrupt":
                # Manual interrupt
                await handle_barge_in(websocket, session)

            # Legacy support for push-to-talk
            elif msg_type == "start_recording":
                session.cancelled = False
                await websocket.send_json({"type": "recording_started"})

            elif msg_type == "stop_recording":
                if "audio" in msg:
                    audio_bytes = base64.b64decode(msg["audio"])
                else:
                    # Use buffered audio from turn detector
                    audio_bytes = None
                if audio_bytes and len(audio_bytes) > 1600:
                    await process_voice_pipeline(websocket, session, audio_bytes)

    except WebSocketDisconnect:
        logger.info("Client ngat ket noi")
    except Exception as e:
        logger.error(f"Loi WebSocket: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        # Cleanup
        if session.pipeline_task and not session.pipeline_task.done():
            session.pipeline_task.cancel()
        session.is_conversation_active = False


async def start_conversation(websocket: WebSocket, session: ConversationSession):
    """Start full-duplex conversation mode."""
    session.is_conversation_active = True
    session.cancelled = False

    # Create turn detector
    session.turn_detector = TurnDetector(vad_service)
    session.turn_detector.start_listening()

    await websocket.send_json({
        "type": "conversation_started",
        "message": "Full-duplex mode active"
    })
    logger.info("Full-duplex conversation started")


async def stop_conversation(websocket: WebSocket, session: ConversationSession):
    """Stop full-duplex conversation."""
    session.is_conversation_active = False
    session.cancelled = True

    # Cancel any running pipeline
    if session.pipeline_task and not session.pipeline_task.done():
        session.pipeline_task.cancel()

    if session.turn_detector:
        session.turn_detector.reset()
        session.turn_detector = None

    session.is_ai_speaking = False

    await websocket.send_json({
        "type": "conversation_stopped",
        "message": "Conversation ended"
    })
    logger.info("Full-duplex conversation stopped")


async def handle_audio_chunk(websocket: WebSocket, session: ConversationSession, chunk: bytes):
    """Process continuous audio chunk through VAD turn detector."""
    if not session.turn_detector:
        return

    # Skip VAD processing while AI is speaking to prevent echo detection.
    # Only process barge-in if we get very strong speech signal.
    if session.is_ai_speaking:
        import numpy as np
        audio_np = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        energy = float(np.sqrt(np.mean(audio_np ** 2)))
        # Only barge-in on very loud speech (user intentionally talking over AI)
        if energy > 0.08 and vad_service.is_speech(audio_np):
            logger.info(f"Barge-in detected (energy={energy:.3f})")
            await handle_barge_in(websocket, session)
        return

    result = session.turn_detector.process_audio(chunk)

    # Send VAD status for visualizer
    await websocket.send_json({
        "type": "vad_status",
        "speaking": result["is_speech"],
        "state": session.turn_detector.state.value
    })

    if result["event"] == "speech_start":
        logger.info("Speech detected - user started talking")
        await websocket.send_json({"type": "turn_start"})

    elif result["event"] == "speech_end":
        logger.info("User finished speaking - processing turn")
        await websocket.send_json({"type": "turn_end"})

        audio_bytes = result["audio"]
        if audio_bytes and len(audio_bytes) > 1600:
            # Process in background so we can keep receiving audio
            if session.pipeline_task and not session.pipeline_task.done():
                session.pipeline_task.cancel()
                try:
                    await session.pipeline_task
                except (asyncio.CancelledError, Exception):
                    pass

            session.cancelled = False
            session.pipeline_task = asyncio.create_task(
                process_voice_pipeline(websocket, session, audio_bytes)
            )


async def handle_barge_in(websocket: WebSocket, session: ConversationSession):
    """Handle user interrupting AI (barge-in)."""
    if session.is_ai_speaking:
        logger.info("Barge-in: user interrupted AI")
        session.cancelled = True
        session.is_ai_speaking = False

        # Cancel running pipeline
        if session.pipeline_task and not session.pipeline_task.done():
            session.pipeline_task.cancel()
            try:
                await session.pipeline_task
            except (asyncio.CancelledError, Exception):
                pass

        await websocket.send_json({"type": "interrupted"})

        # Resume listening after barge-in
        if session.turn_detector and session.is_conversation_active:
            session.turn_detector.start_listening()


async def process_voice_pipeline(websocket: WebSocket, session: ConversationSession, audio_bytes: bytes):
    """Full pipeline: Audio -> STT -> LLM -> TTS -> Audio out"""
    async with session.pipeline_lock:
        try:
            # Mark AI as speaking early to stop frontend from sending audio
            session.is_ai_speaking = True

            # ── Step 1: STT ──
            await websocket.send_json({
                "type": "status",
                "stage": "stt",
                "message": "Dang nhan dang giong noi..."
            })

            user_text = await stt_service.transcribe(audio_bytes)

            if not user_text or user_text.strip() == "":
                session.is_ai_speaking = False
                await websocket.send_json({
                    "type": "error",
                    "message": "Khong nghe ro, vui long noi lai"
                })
                await websocket.send_json({"type": "audio_done"})
                # Resume listening
                if session.turn_detector and session.is_conversation_active:
                    session.turn_detector.start_listening()
                return

            await websocket.send_json({"type": "transcript_user", "text": user_text})
            session.add_message("user", user_text)
            logger.info(f"User: {user_text}")

            # Retrieve context from RAG (safe fallback to normal LLM flow)
            rag_context = ""
            rag_sources = []
            if rag_service and rag_service.is_ready:
                rag_context, rag_sources = await rag_service.retrieve(user_text)

            llm_messages = session.conversation_history
            if rag_context and rag_service:
                rag_prompt = rag_service.build_rag_prompt(user_text, rag_context, rag_sources)
                if rag_prompt:
                    llm_messages = [
                        {
                            "role": "system",
                            "content": rag_prompt
                        },
                        *session.conversation_history
                    ]

            # ── Step 2: LLM (streaming) ──
            await websocket.send_json({
                "type": "status",
                "stage": "llm",
                "message": "Dang suy nghi..."
            })

            session.is_ai_speaking = True
            session.cancelled = False
            full_response = ""
            sentence_buffer = ""

            async for chunk_text in llm_service.stream_response(llm_messages):
                if session.cancelled:
                    break

                full_response += chunk_text
                sentence_buffer += chunk_text

                # Send partial text for real-time display
                await websocket.send_json({
                    "type": "transcript_ai_partial",
                    "text": chunk_text,
                    "full_text": full_response
                })

                # ── Step 3: TTS per sentence ──
                sentences = split_sentences(sentence_buffer)
                if len(sentences) > 1:
                    for sent in sentences[:-1]:
                        if sent.strip() and not session.cancelled:
                            await generate_and_send_audio(websocket, session, sent.strip())
                    sentence_buffer = sentences[-1]

            # Send remaining buffer
            if sentence_buffer.strip() and not session.cancelled:
                await generate_and_send_audio(websocket, session, sentence_buffer.strip())

            if not session.cancelled:
                session.add_message("assistant", full_response)
                await websocket.send_json({
                    "type": "transcript_ai",
                    "text": full_response,
                    "done": True
                })
                logger.info(f"AI: {full_response[:80]}...")

            await websocket.send_json({"type": "audio_done"})
            session.is_ai_speaking = False

            # Resume listening after AI finishes
            if session.turn_detector and session.is_conversation_active:
                session.turn_detector.start_listening()

        except asyncio.CancelledError:
            logger.info("Pipeline cancelled (barge-in)")
            session.is_ai_speaking = False
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            await websocket.send_json({"type": "error", "message": f"Loi xu ly: {str(e)}"})
            session.is_ai_speaking = False
            # Resume listening after error
            if session.turn_detector and session.is_conversation_active:
                session.turn_detector.start_listening()


async def generate_and_send_audio(websocket: WebSocket, session: ConversationSession, text: str):
    """Generate TTS audio and stream to client."""
    try:
        logger.info(f"TTS generating: {text[:50]}...")
        audio_data = await tts_service.synthesize(text, voice=session.voice)
        logger.info(f"TTS done: {len(audio_data)} bytes")
        if audio_data and not session.cancelled:
            chunk_size = 8192
            for i in range(0, len(audio_data), chunk_size):
                if session.cancelled:
                    break
                chunk = audio_data[i:i + chunk_size]
                await websocket.send_json({
                    "type": "audio_chunk",
                    "data": base64.b64encode(chunk).decode("utf-8"),
                    "format": "mp3"
                })
                await asyncio.sleep(0.01)
    except Exception as e:
        logger.error(f"TTS error: {e}")


def split_sentences(text: str) -> list[str]:
    """Split Vietnamese text into sentences for streaming TTS."""
    import re
    parts = re.split(r'([.!?;])\s*', text)
    sentences = []
    current = ""
    for part in parts:
        current += part
        if part in ".!?;":
            sentences.append(current)
            current = ""
    if current:
        sentences.append(current)
    return sentences


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)