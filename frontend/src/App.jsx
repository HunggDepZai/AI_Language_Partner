import React from 'react'
import { useVoiceChat } from './hooks/useVoiceChat.js'
import ChatMessages from './components/ChatMessages.jsx'
import VoiceControl from './components/VoiceControl.jsx'

export default function App() {
  const {
    status, messages, currentAiText, isConnected,
    isConversationActive, vadSpeaking, voice, error,
    connect, toggleConversation, interrupt,
    updateConfig, clearMessages,
  } = useVoiceChat()

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <span className="header-flag">🇻🇳</span>
          <h1>Tro Ly AI Tieng Viet</h1>
        </div>
        <div className="header-right">
          <span className={`connection-badge ${isConnected ? 'connected' : ''}`}>
            {isConnected ? '● Da ket noi' : '○ Chua ket noi'}
          </span>
        </div>
      </header>

      {/* Chat area */}
      <main className="app-main">
        <ChatMessages messages={messages} currentAiText={currentAiText} />
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
          onVoiceChange={(v) => updateConfig(v)}
          onClearMessages={clearMessages}
        />
      </footer>
    </div>
  )
}