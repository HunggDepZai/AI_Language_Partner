"""
LLM Service - GPT-4o / Claude streaming for Vietnamese conversations.
Supports OpenAI, Groq, and local Ollama backends.
"""
import os
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Bạn là một trợ lý AI thông minh, thân thiện, nói tiếng Việt tự nhiên.

Quy tắc:
- Luôn trả lời bằng tiếng Việt trừ khi người dùng yêu cầu ngôn ngữ khác
- Trả lời ngắn gọn, súc tích (1-3 câu cho câu hỏi đơn giản)
- Giọng điệu thân thiện, tự nhiên như đang nói chuyện
- Không dùng markdown, emoji hay ký tự đặc biệt (vì output sẽ được đọc thành giọng nói)
- Dùng dấu chấm, phẩy, chấm hỏi, chấm than bình thường
- Nếu không biết câu trả lời, hãy nói thật thay vì bịa đặt
- Xưng hô "tôi" và gọi người dùng là "bạn"
"""


class LLMService:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "500"))
        logger.info(f"✅ LLM Service: {self.provider} / {self.model}")

    async def stream_response(self, conversation_history: list[dict]) -> AsyncGenerator[str, None]:
        """Stream LLM response chunk by chunk."""
        if self.provider == "groq":
            async for chunk in self._stream_groq(conversation_history):
                yield chunk
        elif self.provider == "ollama":
            async for chunk in self._stream_ollama(conversation_history):
                yield chunk
        else:
            async for chunk in self._stream_openai(conversation_history):
                yield chunk

    async def _stream_openai(self, conversation_history: list[dict]) -> AsyncGenerator[str, None]:
        """Stream from OpenAI GPT-4o."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

        stream = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _stream_groq(self, conversation_history: list[dict]) -> AsyncGenerator[str, None]:
        """Stream from Groq (Llama/Mixtral - very fast)."""
        from groq import AsyncGroq
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

        stream = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _stream_ollama(self, conversation_history: list[dict]) -> AsyncGenerator[str, None]:
        """Stream from local Ollama server."""
        import httpx

        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens,
                    }
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
