# Vietnamese Voice AI Assistant

A web-based AI voice assistant for Vietnamese conversations, combining speech processing, large language models, and text-to-speech technologies in a full-stack application.

## Overview

**Vietnamese Voice AI Assistant** is a project exploring how modern AI technologies can be integrated into a conversational voice application.

The system connects a React frontend to a Python backend through WebSocket communication. Its voice-processing pipeline combines Voice Activity Detection (VAD), Speech-to-Text (STT), Large Language Models (LLM), and Text-to-Speech (TTS).

The project supports OpenAI and Groq as AI service providers, with Edge-TTS for speech synthesis.

## Key Features

- **Vietnamese Voice Interaction** – Designed for voice-based conversations in Vietnamese.
- **Speech Recognition** – Supports OpenAI and Groq speech recognition providers.
- **AI-Powered Responses** – Integrates OpenAI and Groq language model providers.
- **Text-to-Speech** – Uses Edge-TTS to generate spoken responses.
- **Voice Activity Detection** – Uses Silero VAD for voice activity detection.
- **WebSocket Communication** – Connects the frontend and backend for voice interaction.
- **Modular Architecture** – Separates voice processing services from the frontend application.

## Tech Stack

| Category | Technologies |
|---|---|
| Programming Languages | Python, JavaScript |
| Backend | FastAPI, Uvicorn |
| Frontend | React 18, Vite |
| Communication | WebSocket |
| Voice Activity Detection | Silero VAD |
| Speech-to-Text | OpenAI, Groq |
| Large Language Model | OpenAI, Groq |
| Text-to-Speech | Edge-TTS |
| AI / Data Processing | LangChain, Qdrant, Sentence Transformers |
| Dependency Management | uv, npm |

## System Architecture

The application follows a client-server architecture with a modular AI processing pipeline.

```text
+--------------------------------------+
|             FRONTEND                 |
|                                      |
|           React + Vite               |
|                                      |
|     Microphone / Audio Interface     |
|                 |                    |
|             WebSocket                 |
+-----------------|--------------------+
                  |
                  v
+--------------------------------------+
|              BACKEND                 |
|                                      |
|             FastAPI                  |
|              Python                  |
|                 |                    |
|                 v                    |
|       +--------------------+         |
|       |   Voice Pipeline   |         |
|       +--------------------+         |
|                 |                    |
|        +--------+--------+           |
|        |        |        |           |
|        v        v        v           |
|       VAD      STT      LLM          |
|        |        |        |           |
|        |        |        v           |
|        |        |   AI Response      |
|        |        |        |           |
|        +--------+--------+           |
|                 |                    |
|                 v                    |
|                TTS                   |
|                 |                    |
|                 v                    |
|           Audio Output               |
+--------------------------------------+
                  |
                  v
             FRONTEND
```

## AI Voice Processing Pipeline

The core processing workflow consists of four main stages:

### 1. Voice Activity Detection (VAD)

Uses Silero VAD to detect voice activity in incoming audio.

### 2. Speech-to-Text (STT)

Converts spoken Vietnamese into text using the configured provider:

- OpenAI
- Groq

### 3. Large Language Model (LLM)

Processes recognized text and generates conversational responses using the configured provider:

- OpenAI
- Groq

### 4. Text-to-Speech (TTS)

Uses Edge-TTS to convert AI-generated text into spoken audio.

```text
Audio Input
    |
    v
Silero VAD
    |
    v
Speech-to-Text
(OpenAI / Groq)
    |
    v
Large Language Model
(OpenAI / Groq)
    |
    v
Edge-TTS
    |
    v
Audio Output
```

## Project Structure

```text
AI_Language_Partner/
|
|-- backend/
|   |-- main.py
|   |-- pyproject.toml
|   |-- uv.lock
|   |-- services/
|   |-- ...
|
|-- frontend/
|   |-- package.json
|   |-- package-lock.json
|   |-- src/
|   |-- ...
|
|-- .env.example
|-- .gitignore
|-- docker-compose.yml
|-- README.md
```

*The structure above highlights the main project files. Some implementation files and directories are omitted for readability.*

## Getting Started

### Prerequisites

Make sure you have installed:

- Python 3.14 or later
- Node.js and npm
- uv
- An OpenAI API key and/or Groq API key, depending on your selected providers

### 1. Clone the Repository

```bash
git clone https://github.com/HunggDepZai/AI_Language_Partner.git

cd AI_Language_Partner
```

### 2. Configure Environment Variables

Create a local environment file from the example:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

Open `.env` and configure the required API credentials and application settings.

For example:

```env
OPENAI_API_KEY=your_openai_api_key
GROQ_API_KEY=your_groq_api_key
```

Use the variable names and configuration options defined in `.env.example` as the source of truth.

**Important:** Never commit your actual `.env` file or expose API keys in source code, screenshots, or public repositories.

### 3. Install Backend Dependencies

From the project root:

```bash
cd backend

uv sync --python 3.14
```

### 4. Install Frontend Dependencies

Open another terminal:

```bash
cd frontend

npm ci
```

### 5. Start the Backend

In the backend terminal:

```bash
cd backend

uv run python main.py
```

The backend is configured to run on:

```text
http://localhost:8000
```

### 6. Start the Frontend

In a separate terminal:

```bash
cd frontend

npm run dev
```

Open the application in your browser:

```text
http://localhost:3000
```

Keep both terminal processes running while using the application.

## Configuration

The application supports the following AI service providers:

| Component | Supported Configuration |
|---|---|
| Voice Activity Detection | Silero VAD |
| Speech-to-Text | OpenAI / Groq |
| Language Model | OpenAI / Groq |
| Text-to-Speech | Edge-TTS |

Provider selection and model settings are managed through environment variables.

Refer to `.env.example` for the exact configuration keys and supported values.

## Development Roadmap

Potential improvements for future development include:

- Improving real-time voice interaction and response latency.
- Enhancing audio streaming and interruption handling.
- Improving speech recognition accuracy for Vietnamese.
- Expanding support for additional AI model providers.
- Adding more Vietnamese text-to-speech options.
- Improving error handling and application reliability.
- Adding automated tests and deployment documentation.
- Enhancing the user interface and conversation experience.

## License

Please refer to the repository's license file for licensing terms.

## Author

**Hung Nguyen**

GitHub: [HunggDepZai](https://github.com/HunggDepZai)

---

*Built to explore AI-powered Vietnamese voice interaction.* 🇻🇳