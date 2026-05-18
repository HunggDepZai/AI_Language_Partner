import { useState, useRef, useCallback, useEffect } from 'react'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/voice`

export function useVoiceChat() {
  // ── State ──
  const [status, setStatus] = useState('idle')
  const [messages, setMessages] = useState([])
  const [currentAiText, setCurrentAiText] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isConversationActive, setIsConversationActive] = useState(false)
  const [vadSpeaking, setVadSpeaking] = useState(false)
  const [voice, setVoice] = useState('female')
  const [error, setError] = useState(null)
  const [analyserNode, setAnalyserNode] = useState(null)
  const [currentSentence, setCurrentSentence] = useState('')

  // ── Refs ──
  const wsRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const processorRef = useRef(null)
  const isPlayingRef = useRef(false)
  const audioChunksRef = useRef([])
  const isConversationActiveRef = useRef(false)
  const currentSourceRef = useRef(null) // Ref để theo dõi node âm thanh đang phát
  const isAiSpeakingRef = useRef(false)

  // ── Initialize AudioContext & Analyser ──
  const initAudio = useCallback(() => {
    if (!audioContextRef.current) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext
      audioContextRef.current = new AudioContextClass({ sampleRate: 16000 })
    }
    if (!analyserRef.current) {
      const analyser = audioContextRef.current.createAnalyser()
      analyser.fftSize = 256
      analyserRef.current = analyser
      setAnalyserNode(analyser)
    }
    return audioContextRef.current
  }, [])

  // Keep ref in sync
  useEffect(() => {
    isConversationActiveRef.current = isConversationActive
  }, [isConversationActive])

  // ── Connect WebSocket ──
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // Khởi tạo Audio sớm để sẵn sàng cho Lip-sync
    const ctx = initAudio();
    console.log('[Audio] AudioContext initialized, state:', ctx.state);

    setStatus('connecting')
    const ws = new WebSocket(WS_URL)
    ws.onopen = () => {
      setIsConnected(true)
      setStatus('ready')
      setError(null)
      ws.send(JSON.stringify({ type: 'config', voice }))
    }
    ws.onmessage = (event) => handleMessage(JSON.parse(event.data))
    ws.onerror = () => {
      setError('Kết nối thất bại. Kiểm tra backend.')
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

  // ── Audio playback ──
  const playAudioQueue = useCallback(async () => {
    if (isPlayingRef.current || audioChunksRef.current.length === 0) return
    isPlayingRef.current = true

    const ctx = initAudio()
    if (ctx.state === 'suspended') await ctx.resume()

    while (audioChunksRef.current.length > 0) {
      const { data, text } = audioChunksRef.current.shift()
      if (text) {
        setCurrentSentence(text)
        console.log('[NaturalSync] Now speaking:', text)
      }

      const binary = atob(data)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

      try {
        const audioBuffer = await ctx.decodeAudioData(bytes.buffer)
        const source = ctx.createBufferSource()
        source.buffer = audioBuffer
        source.connect(analyserRef.current)
        analyserRef.current.connect(ctx.destination)

        currentSourceRef.current = source
        await new Promise((resolve) => {
          source.onended = () => {
            currentSourceRef.current = null
            resolve()
          }
          source.start(0)
        })
      } catch (err) {
        console.error('[Audio] Decode error:', err)
      }
    }
    isPlayingRef.current = false
    setCurrentSentence('') // Clear sentence when done

    // Khi hết tiếng, nếu vẫn đang ở trạng thái ai_speaking thì chuyển về listening/ready
    if (isAiSpeakingRef.current === false) {
      setStatus(isConversationActiveRef.current ? 'listening' : 'ready')
    }
  }, [initAudio])

  const stopAudioPlayback = useCallback(() => {
    audioChunksRef.current = []
    isPlayingRef.current = false
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.stop()
      } catch (e) {
        // Source might have already stopped
      }
      currentSourceRef.current = null
    }
  }, [])

  const stopMicrophone = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(t => t.stop())
      mediaStreamRef.current = null
    }
  }, [])

  const stopConversationAction = useCallback(() => {
    if (isConversationActiveRef.current) {
      stopAudioPlayback()
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'stop_conversation' }))
      }
      stopMicrophone()
      setIsConversationActive(false)
      isConversationActiveRef.current = false
      setStatus('ready')
    }
  }, [stopAudioPlayback, stopMicrophone])

  // ── Handle messages ──
  const handleMessage = useCallback((msg) => {
    switch (msg.type) {
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

        // --- ADDED STOP KEYWORD LOGIC ---
        const lowerText = msg.text.toLowerCase();
        if (lowerText.includes('tạm biệt') || lowerText.includes('tắt mic') || lowerText.includes('ngừng nghe') || lowerText.includes('đi ngủ đi')) {
          console.log('[VoiceChat] Phát hiện từ khóa dừng cuộc gọi:', msg.text);
          stopConversationAction();
        }
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
        // Lưu trữ cả audio và text (nếu có)
        audioChunksRef.current.push({
          data: msg.data,
          text: msg.text
        })
        playAudioQueue()
        break
      case 'audio_done':
        isAiSpeakingRef.current = false
        // Chỉ chuyển trạng thái nếu không còn audio đang phát
        if (!isPlayingRef.current) {
          setStatus(isConversationActiveRef.current ? 'listening' : 'ready')
        }
        break
      case 'vad_status':
        setVadSpeaking(msg.speaking)
        break
      case 'interrupted':
        isAiSpeakingRef.current = false
        stopAudioPlayback()
        setStatus(isConversationActiveRef.current ? 'listening' : 'ready')
        break
      case 'error':
        setError(msg.message)
        setStatus(isConversationActiveRef.current ? 'listening' : 'ready')
        break
    }
  }, [playAudioQueue, stopAudioPlayback])

  // ── Microphone ──
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

      const ctx = initAudio()
      const actualRate = ctx.sampleRate
      const targetRate = 16000
      const needsResample = Math.abs(actualRate - targetRate) > 100

      const source = ctx.createMediaStreamSource(stream)
      const processor = ctx.createScriptProcessor(4096, 1, 1)

      processor.onaudioprocess = (e) => {
        if (wsRef.current?.readyState === WebSocket.OPEN && isConversationActiveRef.current) {
          // NOTE: streaming mic during AI speech enables vocal barge-in. The
          // backend gates these chunks behind an energy + N-consecutive-frame
          // check so AEC residue from the speaker doesn't trigger false stops.
          let float32 = e.inputBuffer.getChannelData(0)
          if (needsResample) {
            const ratio = actualRate / targetRate
            const newLen = Math.round(float32.length / ratio)
            const resampled = new Float32Array(newLen)
            for (let i = 0; i < newLen; i++) {
              resampled[i] = float32[Math.min(Math.round(i * ratio), float32.length - 1)]
            }
            float32 = resampled
          }
          const int16 = new Int16Array(float32.length)
          for (let i = 0; i < float32.length; i++) {
            int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32768)))
          }
          const base64 = btoa(String.fromCharCode(...new Uint8Array(int16.buffer)))
          wsRef.current.send(JSON.stringify({ type: 'audio_chunk', data: base64 }))
        }
      }

      source.connect(processor)
      processor.connect(ctx.destination)
      processorRef.current = processor
      return true
    } catch (err) {
      setError('Không truy cập được microphone.')
      return false
    }
  }, [initAudio])



  const toggleConversation = useCallback(async (withGreeting = false) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connect()
      return
    }
    if (isConversationActive) {
      stopConversationAction()
    } else {
      stopAudioPlayback()
      const micOk = await startMicrophone()
      if (!micOk) return
      wsRef.current.send(JSON.stringify({ type: 'start_conversation', greeting: withGreeting }))
      setIsConversationActive(true)
      isConversationActiveRef.current = true
      setStatus(withGreeting ? 'ai_speaking' : 'listening')
    }
  }, [isConversationActive, connect, startMicrophone, stopMicrophone, stopAudioPlayback])

  const interrupt = useCallback(() => {
    stopAudioPlayback()
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'interrupt' }))
    }
  }, [stopAudioPlayback])

  const sendTextMessage = useCallback((text) => {
    if (!text.trim()) return
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connect()
      // Note: We might want to wait for connection here, but for now simple
      setTimeout(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'chat_message', text }))
        }
      }, 1000)
    } else {
      wsRef.current.send(JSON.stringify({ type: 'chat_message', text }))
    }
    // Optimistic UI update already handled by transcript_user message from server
    // but we can also set status to show we're sending
    setStatus('processing')
  }, [connect])

  const updateConfig = useCallback((newVoice) => {
    if (newVoice) setVoice(newVoice)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'config', voice: newVoice || voice }))
    }
  }, [voice])

  const clearMessages = useCallback(() => {
    setMessages([])
    setCurrentAiText('')
  }, [])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
      stopMicrophone()
      audioContextRef.current?.close()
    }
  }, [stopMicrophone])

  return {
    status, messages, currentAiText, currentSentence, isConnected,
    isConversationActive, vadSpeaking, voice, error,
    connect, toggleConversation, interrupt, sendTextMessage,
    updateConfig, clearMessages,
    analyser: analyserNode
  }
}