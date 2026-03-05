import { useState, useRef, useCallback, useEffect } from 'react'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/voice`

export function useVoiceChat() {
  // ── State ──
  const [status, setStatus] = useState('idle')
  // idle, connecting, ready, listening, user_speaking, processing, ai_speaking
  const [messages, setMessages] = useState([])
  const [currentAiText, setCurrentAiText] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isConversationActive, setIsConversationActive] = useState(false)
  const [vadSpeaking, setVadSpeaking] = useState(false)
  const [voice, setVoice] = useState('female')
  const [error, setError] = useState(null)

  // ── Refs ──
  const wsRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const audioContextRef = useRef(null)
  const processorRef = useRef(null)
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const audioPlayerRef = useRef(null)
  const audioChunksRef = useRef([])
  const isConversationActiveRef = useRef(false)
  const isAiSpeakingRef = useRef(false)

  // Keep ref in sync with state
  useEffect(() => {
    isConversationActiveRef.current = isConversationActive
  }, [isConversationActive])

  // ── Connect WebSocket ──
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setStatus('connecting')
    const ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      setIsConnected(true)
      setStatus('ready')
      setError(null)
      ws.send(JSON.stringify({ type: 'config', voice }))
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      handleMessage(msg)
    }

    ws.onerror = () => {
      setError('Khong ket noi duoc server. Hay kiem tra backend dang chay.')
      setIsConnected(false)
      setStatus('idle')
    }

    ws.onclose = () => {
      setIsConnected(false)
      setStatus('idle')
      setIsConversationActive(false)
      isConversationActiveRef.current = false
    }

    wsRef.current = ws
  }, [voice])

  // ── Handle incoming messages ──
  const handleMessage = useCallback((msg) => {
    switch (msg.type) {
      case 'conversation_started':
        setStatus('listening')
        break

      case 'conversation_stopped':
        setStatus('ready')
        break

      case 'turn_start':
        setStatus('user_speaking')
        break

      case 'turn_end':
        setStatus('processing')
        break

      case 'status':
        if (msg.stage === 'stt') setStatus('processing')
        if (msg.stage === 'llm') {
          setStatus('ai_speaking')
          isAiSpeakingRef.current = true
        }
        break

      case 'transcript_user':
        setMessages(prev => [...prev, { role: 'user', text: msg.text }])
        setCurrentAiText('')
        break

      case 'transcript_ai_partial':
        setCurrentAiText(msg.full_text)
        setStatus('ai_speaking')
        break

      case 'transcript_ai':
        if (msg.done) {
          setMessages(prev => [...prev, { role: 'assistant', text: msg.text }])
          setCurrentAiText('')
        }
        break

      case 'audio_chunk':
        audioChunksRef.current.push(msg.data)
        playAudioQueue()
        break

      case 'audio_done':
        isAiSpeakingRef.current = false
        // After AI finishes, go back to listening if conversation is active
        if (isConversationActiveRef.current) {
          setStatus('listening')
        } else {
          setStatus('ready')
        }
        break

      case 'vad_status':
        setVadSpeaking(msg.speaking)
        break

      case 'interrupted':
        isAiSpeakingRef.current = false
        stopAudioPlayback()
        if (isConversationActiveRef.current) {
          setStatus('listening')
        } else {
          setStatus('ready')
        }
        break

      case 'error':
        setError(msg.message)
        if (isConversationActiveRef.current) {
          setStatus('listening')
        } else {
          setStatus('ready')
        }
        break

      // Legacy
      case 'recording_started':
        setStatus('user_speaking')
        break
    }
  }, [])

  // ── Audio playback ──
  const playAudioQueue = useCallback(async () => {
    if (isPlayingRef.current || audioChunksRef.current.length === 0) return
    isPlayingRef.current = true

    while (audioChunksRef.current.length > 0) {
      const base64 = audioChunksRef.current.shift()
      const binary = atob(base64)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

      const blob = new Blob([bytes], { type: 'audio/mp3' })
      const url = URL.createObjectURL(blob)

      await new Promise((resolve) => {
        const audio = new Audio(url)
        audioPlayerRef.current = audio
        audio.onended = () => {
          URL.revokeObjectURL(url)
          resolve()
        }
        audio.onerror = () => {
          URL.revokeObjectURL(url)
          resolve()
        }
        audio.play().catch(resolve)
      })
    }

    isPlayingRef.current = false
  }, [])

  const stopAudioPlayback = useCallback(() => {
    audioChunksRef.current = []
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause()
      audioPlayerRef.current = null
    }
    isPlayingRef.current = false
  }, [])

  // ── Start microphone (always-on for full-duplex) ──
  const startMicrophone = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      })
      mediaStreamRef.current = stream

      const audioContext = new AudioContext({ sampleRate: 16000 })
      audioContextRef.current = audioContext

      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)

      processor.onaudioprocess = (e) => {
        if (wsRef.current?.readyState === WebSocket.OPEN && isConversationActiveRef.current) {
          // Don't send audio while AI is speaking to avoid echo feedback loop
          if (isAiSpeakingRef.current) return

          const float32 = e.inputBuffer.getChannelData(0)
          const int16 = new Int16Array(float32.length)
          for (let i = 0; i < float32.length; i++) {
            int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32768)))
          }
          const base64 = btoa(String.fromCharCode(...new Uint8Array(int16.buffer)))
          wsRef.current.send(JSON.stringify({ type: 'audio_chunk', data: base64 }))
        }
      }

      source.connect(processor)
      processor.connect(audioContext.destination)
      processorRef.current = processor

      return true
    } catch (err) {
      setError('Khong truy cap duoc microphone. Hay cho phep quyen truy cap.')
      return false
    }
  }, [])

  const stopMicrophone = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(t => t.stop())
      mediaStreamRef.current = null
    }
  }, [])

  // ── Toggle conversation (main action) ──
  const toggleConversation = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connect()
      return
    }

    if (isConversationActive) {
      // Stop conversation
      stopAudioPlayback()
      wsRef.current.send(JSON.stringify({ type: 'stop_conversation' }))
      stopMicrophone()
      setIsConversationActive(false)
      isConversationActiveRef.current = false
      setStatus('ready')
      setVadSpeaking(false)
    } else {
      // Start conversation
      stopAudioPlayback()
      setError(null)

      const micOk = await startMicrophone()
      if (!micOk) return

      wsRef.current.send(JSON.stringify({ type: 'start_conversation' }))
      setIsConversationActive(true)
      isConversationActiveRef.current = true
      setStatus('listening')
    }
  }, [isConversationActive, connect, startMicrophone, stopMicrophone, stopAudioPlayback])

  // ── Manual interrupt (tap while AI speaking) ──
  const interrupt = useCallback(() => {
    stopAudioPlayback()
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'interrupt' }))
    }
  }, [stopAudioPlayback])

  // ── Voice change ──
  const updateConfig = useCallback((newVoice) => {
    if (newVoice) setVoice(newVoice)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'config',
        voice: newVoice || voice,
      }))
    }
  }, [voice])

  const clearMessages = useCallback(() => {
    setMessages([])
    setCurrentAiText('')
  }, [])

  // ── Cleanup ──
  useEffect(() => {
    return () => {
      wsRef.current?.close()
      mediaStreamRef.current?.getTracks().forEach(t => t.stop())
      audioContextRef.current?.close()
    }
  }, [])

  return {
    status, messages, currentAiText, isConnected,
    isConversationActive, vadSpeaking, voice, error,
    connect, toggleConversation, interrupt,
    updateConfig, clearMessages,
  }
}