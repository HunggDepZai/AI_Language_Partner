import React, { useEffect, useRef } from 'react'
import { useVoiceChat } from './hooks/useVoiceChat.js'
import { useWakeword } from './hooks/useWakeword.js'
import ChatMessages from './components/ChatMessages.jsx'
import VoiceControl from './components/VoiceControl.jsx'
import VrmViewer from './components/VrmViewer.jsx'
import ChatInput from './components/ChatInput.jsx'

export default function App() {
  const {
    status, messages, currentAiText, currentSentence, isConnected,
    isConversationActive, vadSpeaking, voice, error,
    connect, toggleConversation, interrupt, sendTextMessage,
    updateConfig, clearMessages, analyser
  } = useVoiceChat()

  const isConversationActiveRef = useRef(false)
  useEffect(() => { isConversationActiveRef.current = isConversationActive }, [isConversationActive])

  const { isLoaded, isListeningForWake, toggleListening, startListening, stopListening } = useWakeword({
    keyword: 'hey_jarvis',
    threshold: 0.5,
    onDetect: ({ keyword, score }) => {
      console.log(`[App] Wake word detected: ${keyword} (${score.toFixed(2)})`)
      if (!isConversationActiveRef.current) {
        if (!isConnectedRef.current) connect()
        setTimeout(() => {
          toggleConversation(true) // true = greeting
        }, 300)
      }
    }
  })

  const isConnectedRef = useRef(false)
  useEffect(() => { isConnectedRef.current = isConnected }, [isConnected])

  // Khi models loaded → tự động bắt đầu lắng nghe
  useEffect(() => {
    if (isLoaded && !isListeningForWake && !isConversationActive) {
      console.log('[App] Models loaded, starting wake word listening...')
      startListening()
    }
  }, [isLoaded])

  // Khi conversation kết thúc → bật lại wake word
  useEffect(() => {
    if (isLoaded && !isConversationActive && !isListeningForWake) {
      const timer = setTimeout(() => {
        console.log('[App] Conversation ended, restarting wake word...')
        startListening()
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [isConversationActive])

  // Khi conversation bắt đầu → tắt wake word (tránh conflict mic)
  useEffect(() => {
    if (isConversationActive && isListeningForWake) {
      stopListening()
    }
  }, [isConversationActive, isListeningForWake, stopListening])

  return (
    <div className="app">
      <VrmViewer analyser={analyser} status={status} />

      {/* Header */}
      {/* <header className="app-header">
        <div className="header-left">
          <h1>Hướng dẫn viên du lịch Tiếng Việt</h1>
        </div>
        <div className="header-right">
          <span className={`connection-badge ${isConnected ? 'connected' : ''}`}>
            {isConnected ? '● Đã kết nối' : '○ Chưa kết nối'}
          </span>
        </div>
      </header> */}

      {/* Chat area */}
      <main className="app-main">
        <ChatMessages messages={messages} currentAiText={currentAiText} />
        <ChatInput
          onSendMessage={sendTextMessage}
          disabled={status === 'processing' || status === 'ai_speaking'}
          isConnected={isConnected}
          isConversationActive={isConversationActive}
          status={status}
          onConnect={connect}
          onToggleConversation={toggleConversation}
          onInterrupt={interrupt}
        />
      </main>

      {/* Voice control panel */}
      <footer className="app-footer">
        <VoiceControl
          status={status}
          isConnected={isConnected}
          isConversationActive={isConversationActive}
          vadSpeaking={vadSpeaking}
          voice={voice}
          error={error}
          onConnect={connect}
          onToggleConversation={toggleConversation}
          onInterrupt={interrupt}
          onVoiceChange={updateConfig}
          onClearMessages={clearMessages}
          isListeningForWake={isListeningForWake}
          onToggleWake={toggleListening}
          isWakeLoaded={isLoaded}
        />
      </footer>
    </div>
  )
}
