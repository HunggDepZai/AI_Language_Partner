"""
Vietnamese Voice AI Assistant - Full-Duplex Backend Server
Pipeline: Continuous Audio → VAD Turn Detection → STT → LLM → TTS → Audio
Supports: barge-in, auto turn detection, no push-to-talk needed.
"""
import asyncio
import base64
import collections
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
        # Counts consecutive mic frames that look like genuine user speech
        # while the assistant is still talking. Drives the barge-in gate.
        self.barge_in_speech_frames = 0
        # Ring buffer of recent mic chunks during AI speech (~2s @ 4096
        # samples / 16kHz). Replayed into the turn detector after barge-in so
        # the start of the user's interrupting utterance reaches STT instead
        # of being lost.
        self.barge_in_audio_buffer: "collections.deque[bytes]" = collections.deque(maxlen=8)

    def add_message(self, role: str, content: str):
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]


@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "Vietnamese Voice AI Full-Duplex dang hoat dong"}


@app.get("/api/health/rag")
async def rag_health():
    if rag_service:
        stats = rag_service.get_stats()
        stats["status"] = "ok" if stats["ready"] else "not_ready"
        return stats
    return {"status": "not_ready", "ready": False}


@app.get("/api/voices")
async def get_voices():
    return {
        "voices": [
            {"id": "female", "name": "Hoai My (Nu)", "code": "vi-VN-HoaiMyNeural"},
            {"id": "male", "name": "Nam Minh (Nam)", "code": "vi-VN-NamMinhNeural"},
        ]
    }


@app.post("/api/chat")
async def chat_api(request: dict):
    """
    REST API for text chat.
    Supports streaming response for better real-time feel.
    """
    text = request.get("text", "")
    history = request.get("conversation_history", [])
    voice = request.get("voice", os.getenv("DEFAULT_VOICE", "female"))

    if not text:
        return {"error": "Trống dữ liệu"}

    # Use a dummy session for the pipeline logic
    session = ConversationSession()
    session.conversation_history = history
    session.voice = voice

    # Step 1: RAG
    rag_context = ""
    rag_sources = []
    if rag_service and rag_service.is_ready:
        try:
            rag_context, rag_sources = await rag_service.retrieve(text)
        except Exception: pass

    rag_prompt = ""
    if rag_context:
        rag_prompt = rag_service.build_rag_prompt(text, rag_context, rag_sources)

    # Step 2: LLM Streaming
    full_response = ""
    async def response_stream():
        nonlocal full_response
        async for chunk in llm_service.stream_response(history, rag_prompt):
            full_response += chunk
            yield chunk

    # For simple REST without SSE, we might just return full JSON,
    # but the user wants it "realtime". For now, let's keep it simple
    # but ensure it's integrated correctly.
    # To truly be realtime, we should use StreamingResponse or keep using WebSocket.

    # If the web FE expects a single JSON response (as it currently does),
    # we have to wait. To fix this, we should change the Web FE to use WS for chat too.
    # But let's provide a basic functional endpoint first.
    full_text = ""
    async for chunk in llm_service.stream_response(history, rag_prompt):
        full_text += chunk

    audio_b64 = ""
    if full_text:
        audio_data = await tts_service.synthesize(full_text, voice=voice)
        if audio_data:
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")

    return {
        "answer": full_text,
        "audio": audio_b64,
        "tts_available": True,
        "sources": rag_sources
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
                with_greeting = msg.get("greeting", False)
                await start_conversation(websocket, session, with_greeting)

            elif msg_type == "stop_conversation":
                # User toggled conversation OFF
                await stop_conversation(websocket, session)

            elif msg_type == "audio_chunk":
                # Continuous audio from client
                if session.is_conversation_active and session.turn_detector:
                    chunk = base64.b64decode(msg["data"])
                    await handle_audio_chunk(websocket, session, chunk)

            elif msg_type == "chat_message":
                # Manual text message from user
                text = msg.get("text", "")
                if text:
                    session.cancelled = False
                    await websocket.send_json({"type": "transcript_user", "text": text})
                    session.add_message("user", text)
                    # Use provided RAG context if available or retrieve new
                    # For simplicity, we trigger the process_voice_pipeline like logic but with text
                    # We can create a version of the pipeline that starts from text
                    await process_text_pipeline(websocket, session, text)

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


async def start_conversation(websocket: WebSocket, session: ConversationSession, with_greeting: bool = False):
    """Start full-duplex conversation mode."""
    session.is_conversation_active = True
    session.cancelled = False
    session.conversation_history = []  # Reset history for new conversation

    # Create turn detector
    session.turn_detector = TurnDetector(vad_service)

    await websocket.send_json({
        "type": "conversation_started",
        "message": "Full-duplex mode active"
    })
    logger.info("Full-duplex conversation started")

    if with_greeting:
        # Send wake word greeting via TTS before listening
        greeting_text = "mình nghe ạ, bạn muốn mình giúp gì không ạ"
        session.is_ai_speaking = True

        await websocket.send_json({
            "type": "transcript_ai_partial",
            "text": greeting_text,
            "full_text": greeting_text
        })
        await websocket.send_json({
            "type": "transcript_ai",
            "text": greeting_text,
            "done": True
        })
        session.add_message("assistant", greeting_text)

        await generate_and_send_audio(websocket, session, greeting_text)
        await websocket.send_json({"type": "audio_done"})
        session.is_ai_speaking = False

    # Start listening after greeting (or immediately if no greeting)
    session.turn_detector.start_listening()


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


_BARGE_IN_ENERGY_THR = float(os.getenv("BARGE_IN_ENERGY", "0.05"))
_BARGE_IN_CONSEC_FRAMES = int(os.getenv("BARGE_IN_FRAMES", "3"))


async def handle_audio_chunk(websocket: WebSocket, session: ConversationSession, chunk: bytes):
    """Process continuous audio chunk through VAD turn detector."""
    if not session.turn_detector:
        return

    # While the assistant is speaking we still receive mic audio (for barge-in)
    # but we don't run the normal turn detector — the AI's own audio leaking
    # back through speakers would produce false speech_start events.
    if session.is_ai_speaking:
        import numpy as np
        audio_np = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        energy = float(np.sqrt(np.mean(audio_np ** 2)))
        # Keep recent chunks so we can replay them into the turn detector if
        # the user does interrupt — otherwise the start of their utterance is
        # lost to the barge-in detector.
        session.barge_in_audio_buffer.append(chunk)
        # Two conditions must hold for a frame to count: loud enough to be the
        # user (not AEC residue) AND Silero confirms it's speech. Even then we
        # require N consecutive frames so a single noise burst won't cut off
        # the assistant.
        if energy > _BARGE_IN_ENERGY_THR and vad_service.is_speech(audio_np):
            session.barge_in_speech_frames += 1
            if session.barge_in_speech_frames >= _BARGE_IN_CONSEC_FRAMES:
                logger.info(
                    f"Barge-in confirmed: {session.barge_in_speech_frames} frames, "
                    f"energy={energy:.3f}"
                )
                replay = list(session.barge_in_audio_buffer)
                session.barge_in_audio_buffer.clear()
                session.barge_in_speech_frames = 0
                await handle_barge_in(websocket, session, replay_audio=replay)
        else:
            # Reset counter on any non-speech frame so isolated bursts don't
            # accumulate over time.
            session.barge_in_speech_frames = 0
        return

    # Not in AI-speaking state — clear any stale counter and run the normal
    # turn detector for end-of-user-turn detection.
    session.barge_in_speech_frames = 0
    if session.barge_in_audio_buffer:
        session.barge_in_audio_buffer.clear()
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


async def handle_barge_in(
    websocket: WebSocket,
    session: ConversationSession,
    replay_audio: Optional[list[bytes]] = None,
):
    """Handle user interrupting AI (barge-in).

    ``replay_audio`` are the mic chunks that triggered the barge-in detection.
    They are fed into the freshly-reset turn detector so the start of the
    interrupting utterance is captured for STT.
    """
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
            if replay_audio:
                # Replay the buffered chunks so the user's first ~700ms of
                # speech reaches STT instead of being discarded.
                emitted_turn_start = False
                for replay_chunk in replay_audio:
                    result = session.turn_detector.process_audio(replay_chunk)
                    if result.get("event") == "speech_start" and not emitted_turn_start:
                        await websocket.send_json({"type": "turn_start"})
                        emitted_turn_start = True


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
                "message": "Đang nhận dạng giọng nói..."
            })

            logger.info(f"STT: nhận {len(audio_bytes)} bytes audio ({len(audio_bytes)/32000:.2f}s)")

            try:
                user_text = await stt_service.transcribe(audio_bytes)
            except Exception as stt_err:
                logger.error(f"STT exception: {stt_err}")
                user_text = ""

            if not user_text or user_text.strip() == "":
                session.is_ai_speaking = False
                logger.info("STT: không nhận ra text, skip pipeline")
                await websocket.send_json({
                    "type": "error",
                    "message": "Không nghe rõ, vui lòng nói lại"
                })
                await websocket.send_json({"type": "audio_done"})
                # Resume listening
                if session.turn_detector and session.is_conversation_active:
                    session.turn_detector.start_listening()
                return

            await websocket.send_json({"type": "transcript_user", "text": user_text})
            session.add_message("user", user_text)
            logger.info(f"User: {user_text}")

            # ── Step 1.5: RAG ──
            await websocket.send_json({
                "type": "status",
                "stage": "rag",
                "message": "Đang tìm kiếm thông tin..."
            })
            rag_system_prompt = ""
            rag_sources = []
            if rag_service and rag_service.is_ready:
                if should_skip_rag(user_text):
                    logger.info(f"RAG: skip chitchat utterance — '{user_text[:60]}'")
                else:
                    try:
                        rag_context, rag_sources = await rag_service.retrieve(user_text)
                        if rag_context:
                            rag_system_prompt = rag_service.build_rag_prompt(user_text, rag_context, rag_sources)
                            logger.info(f"RAG: inject context ({len(rag_context)} ký tự, {len(rag_sources)} nguồn)")
                    except Exception as rag_err:
                        logger.warning(f"RAG retrieve lỗi, fallback LLM thường: {rag_err}")

            # ── Step 2: LLM (streaming) ──
            await websocket.send_json({
                "type": "status",
                "stage": "llm",
                "message": "Dang suy nghi..."
            })

            session.is_ai_speaking = True
            session.cancelled = False

            full_response = await stream_llm_to_tts(websocket, session, rag_system_prompt)

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


async def process_text_pipeline(websocket: WebSocket, session: ConversationSession, text: str):
    """Pipeline starting from text - skips STT."""
    async with session.pipeline_lock:
        try:
            session.is_ai_speaking = True
            
            # ── Step 1.5: RAG ──
            await websocket.send_json({
                "type": "status",
                "stage": "rag",
                "message": "Đang tìm kiếm thông tin..."
            })
            rag_system_prompt = ""
            rag_sources = []
            if rag_service and rag_service.is_ready:
                if should_skip_rag(text):
                    logger.info(f"RAG: skip chitchat utterance — '{text[:60]}'")
                else:
                    try:
                        rag_context, rag_sources = await rag_service.retrieve(text)
                        if rag_context:
                            rag_system_prompt = rag_service.build_rag_prompt(text, rag_context, rag_sources)
                    except Exception as e:
                        logger.warning(f"RAG error: {e}")

            # ── Step 2: LLM (streaming) ──
            await websocket.send_json({
                "type": "status",
                "stage": "llm",
                "message": "Đang suy nghĩ..."
            })

            session.is_ai_speaking = True
            session.cancelled = False

            full_response = await stream_llm_to_tts(websocket, session, rag_system_prompt)

            if not session.cancelled:
                session.add_message("assistant", full_response)
                await websocket.send_json({
                    "type": "transcript_ai",
                    "text": full_response,
                    "done": True
                })

            await websocket.send_json({"type": "audio_done"})
            session.is_ai_speaking = False
            if session.turn_detector and session.is_conversation_active:
                session.turn_detector.start_listening()
        except Exception as e:
            logger.error(f"Text pipeline error: {e}")
            session.is_ai_speaking = False
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
                    "format": "mp3",
                    "text": text if i == 0 else None # Gửi text kèm segment đầu tiên
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


# Phrases that indicate chitchat (greeting / farewell / acknowledgement). When
# the user's utterance is *only* one of these, we skip the RAG pipeline because
# embedding+vector search produces no useful signal and just burns latency.
_CHITCHAT_PATTERNS = (
    "xin chào", "chào bạn", "chào em", "chào anh", "chào chị", "chào cô", "chào bé",
    "tạm biệt", "hẹn gặp lại", "bye", "goodbye",
    "cảm ơn", "cám ơn", "thanks", "thank you",
    "ok bạn", "okie", "vâng", "dạ vâng", "ừ",
    "hi bạn", "hello bạn",
    "đi ngủ", "tắt mic", "ngừng nghe",
)
# Inquiry signals — if any of these appear, we treat the utterance as a real
# question and let RAG run even if it also contains chitchat.
_INQUIRY_HINTS = (
    "hiện vật", "bảo tàng", "trưng bày", "cổ vật", "bộ sưu tập",
    "thông tin", "giới thiệu", "kể", "mô tả", "cho tôi", "cho mình", "cho biết",
    "là gì", "thế nào", "ra sao", "ở đâu", "khi nào", "tại sao", "vì sao",
    "bao nhiêu", "mấy", "có không", "có phải",
    "nhóm", "thời", "niên đại", "chất liệu",
)


def should_skip_rag(text: str) -> bool:
    """Heuristic: skip RAG retrieval when the utterance is pure chitchat.

    Why: vector search over greetings/farewells returns negative-score noise
    and BM25 latches onto stop-words like "lại"/"chào", producing irrelevant
    context that wastes API calls and confuses the LLM.
    """
    t = (text or "").lower().strip(" .,!?")
    if not t:
        return True
    # Real questions — never skip, even if wrapped in pleasantries.
    if any(kw in t for kw in _INQUIRY_HINTS):
        return False
    # Very short utterances are almost always acks/chitchat.
    if len(t) < 12 and len(t.split()) <= 3:
        return True
    # Pure chitchat: text matches a known pattern and has no other content.
    if any(p in t for p in _CHITCHAT_PATTERNS):
        # If the chitchat phrase covers most of the utterance, skip.
        for p in _CHITCHAT_PATTERNS:
            if p in t and len(t) <= len(p) + 15:  # allow small filler like "và"
                return True
    return False


# Strong delimiters end a clause unambiguously — split as soon as we see one.
_STRONG_DELIMS = set(".!?;\n")
# Soft delimiters (commas, colons, em/en dashes) only justify a split when the
# segment is already long enough to be worth synthesising on its own.
_SOFT_DELIMS = set(",:—–")


def _is_numeric_separator(buffer: str, i: int) -> bool:
    """``.`` or ``,`` between two digits — Vietnamese thousands or decimal separator.

    If the buffer ends right after the punctuation we cannot yet know whether a
    digit follows, so we conservatively treat it as a separator and wait for
    more text to arrive (returns True). That avoids splitting "khoảng 2." mid-
    number when only the prefix has streamed in.
    """
    n = len(buffer)
    if not (0 < i < n) or not buffer[i - 1].isdigit():
        return False
    if i == n - 1:
        return True  # ambiguous tail — defer the split
    return buffer[i + 1].isdigit()


def find_tts_split(buffer: str, min_soft_len: int = 12) -> int:
    """Find the earliest natural boundary suitable for streaming TTS.

    Returns an index *into buffer* such that ``buffer[:idx]`` is ready to send
    to TTS and ``buffer[idx:]`` should keep accumulating. Returns ``-1`` when
    no boundary has appeared yet.

    Strong delimiters split immediately; soft delimiters only count after the
    candidate segment is at least ``min_soft_len`` characters so we don't ship
    pointlessly short fragments to the synthesiser. Periods/commas embedded in
    numbers (Vietnamese thousands/decimal separators) are skipped.
    """
    n = len(buffer)
    for i, ch in enumerate(buffer):
        if ch in _STRONG_DELIMS:
            if ch == "." and _is_numeric_separator(buffer, i):
                continue
            end = i + 1
            while end < n and buffer[end].isspace():
                end += 1
            return end
    for i, ch in enumerate(buffer):
        if ch in _SOFT_DELIMS and (i + 1) >= min_soft_len:
            if ch == "," and _is_numeric_separator(buffer, i):
                continue
            end = i + 1
            while end < n and buffer[end].isspace():
                end += 1
            return end
    return -1


async def stream_llm_to_tts(
    websocket: WebSocket,
    session: ConversationSession,
    rag_system_prompt: str,
) -> str:
    """Stream LLM response to client and dispatch TTS in the background.

    Returns the full assistant response. The TTS worker runs concurrently so
    the LLM keeps producing tokens while earlier segments are being synthesised.
    """
    full_response = ""
    sentence_buffer = ""
    tts_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    async def tts_worker() -> None:
        while True:
            segment = await tts_queue.get()
            if segment is None:
                return
            if session.cancelled:
                continue
            await generate_and_send_audio(websocket, session, segment)

    worker = asyncio.create_task(tts_worker())

    try:
        async for chunk_text in llm_service.stream_response(session.conversation_history, rag_system_prompt):
            if session.cancelled:
                break

            full_response += chunk_text
            sentence_buffer += chunk_text

            await websocket.send_json({
                "type": "transcript_ai_partial",
                "text": chunk_text,
                "full_text": full_response,
            })

            while True:
                idx = find_tts_split(sentence_buffer)
                if idx == -1:
                    break
                segment = sentence_buffer[:idx].strip()
                sentence_buffer = sentence_buffer[idx:]
                if segment:
                    await tts_queue.put(segment)

        if sentence_buffer.strip() and not session.cancelled:
            await tts_queue.put(sentence_buffer.strip())
    finally:
        # On barge-in we want the worker to exit *now* — cancelling the task
        # propagates CancelledError into any in-flight Edge-TTS synthesize call
        # so audio stops within tens of milliseconds instead of waiting for the
        # current segment to finish (~1-2s).
        if session.cancelled and not worker.done():
            worker.cancel()
        else:
            await tts_queue.put(None)
        try:
            await worker
        except asyncio.CancelledError:
            pass

    return full_response


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)