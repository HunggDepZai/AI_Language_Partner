import React from 'react'
import AudioVisualizer from './AudioVisualizer.jsx'

const STATUS_TEXT = {
  idle: 'Chua ket noi',
  connecting: 'Dang ket noi...',
  ready: 'San sang',
  listening: 'Dang lang nghe...',
  user_speaking: 'Ban dang noi...',
  processing: 'Dang nhan dang...',
  ai_speaking: 'Tro ly dang tra loi...',
}

const STATUS_COLOR = {
  idle: '#6b7280',
  connecting: '#f59e0b',
  ready: '#10b981',
  listening: '#10b981',
  user_speaking: '#ef4444',
  processing: '#f59e0b',
  ai_speaking: '#3b82f6',
}

export default function VoiceControl({
  status, isConnected, isConversationActive, vadSpeaking,
  voice, error,
  onConnect, onToggleConversation, onInterrupt,
  onVoiceChange, onClearMessages
}) {

  const handleMainButton = () => {
    if (!isConnected) {
      onConnect()
      return
    }

    // If AI is speaking and conversation is active, interrupt
    if (status === 'ai_speaking' && isConversationActive) {
      onInterrupt()
      return
    }

    // Toggle conversation on/off
    onToggleConversation()
  }

  const isListening = status === 'listening'
  const isUserSpeaking = status === 'user_speaking'
  const isAiSpeaking = status === 'ai_speaking'
  const isProcessing = status === 'processing'
  const isBusy = isProcessing || isAiSpeaking

  return (
    <div className="voice-control">
      {/* Status indicator */}
      <div className="status-bar">
        <span
          className="status-dot"
          style={{ backgroundColor: STATUS_COLOR[status] }}
        />
        <span className="status-text">{STATUS_TEXT[status]}</span>
        {isConversationActive && (
          <span className="mode-badge">FULL-DUPLEX</span>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {/* Audio visualizer */}
      <AudioVisualizer
        status={status}
        vadSpeaking={vadSpeaking}
        isConversationActive={isConversationActive}
      />

      {/* Main conversation button */}
      <div className="mic-container">
        <button
          className={`mic-button ${
            isConversationActive
              ? isUserSpeaking
                ? 'mic-user-speaking'
                : isAiSpeaking
                  ? 'mic-ai-speaking'
                  : isListening
                    ? 'mic-listening'
                    : 'mic-active'
              : ''
          } ${isBusy && !isConversationActive ? 'mic-busy' : ''}`}
          onClick={handleMainButton}
          disabled={status === 'connecting'}
          title={
            !isConnected ? 'Nhan de ket noi' :
            isConversationActive ? 'Nhan de dung cuoc tro chuyen' :
            'Nhan de bat dau tro chuyen'
          }
        >
          {!isConnected ? (
            /* Connect icon */
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          ) : isConversationActive ? (
            isAiSpeaking ? (
              /* Pause/interrupt icon */
              <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
                <rect x="5" y="3" width="4" height="18" rx="1" />
                <rect x="15" y="3" width="4" height="18" rx="1" />
              </svg>
            ) : (
              /* Active conversation - waveform icon */
              <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
                <rect x="2" y="9" width="3" height="6" rx="1.5">
                  <animate attributeName="height" values="6;12;6" dur="0.8s" repeatCount="indefinite" />
                  <animate attributeName="y" values="9;6;9" dur="0.8s" repeatCount="indefinite" />
                </rect>
                <rect x="7" y="7" width="3" height="10" rx="1.5">
                  <animate attributeName="height" values="10;4;10" dur="0.6s" repeatCount="indefinite" />
                  <animate attributeName="y" values="7;10;7" dur="0.6s" repeatCount="indefinite" />
                </rect>
                <rect x="12" y="5" width="3" height="14" rx="1.5">
                  <animate attributeName="height" values="14;8;14" dur="0.7s" repeatCount="indefinite" />
                  <animate attributeName="y" values="5;8;5" dur="0.7s" repeatCount="indefinite" />
                </rect>
                <rect x="17" y="7" width="3" height="10" rx="1.5">
                  <animate attributeName="height" values="10;4;10" dur="0.5s" repeatCount="indefinite" />
                  <animate attributeName="y" values="7;10;7" dur="0.5s" repeatCount="indefinite" />
                </rect>
                <rect x="22" y="9" width="3" height="6" rx="1.5">
                  <animate attributeName="height" values="6;12;6" dur="0.9s" repeatCount="indefinite" />
                  <animate attributeName="y" values="9;6;9" dur="0.9s" repeatCount="indefinite" />
                </rect>
              </svg>
            )
          ) : (
            /* Mic icon - start conversation */
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="2" width="6" height="12" rx="3" />
              <path d="M5 10a7 7 0 0 0 14 0" />
              <line x1="12" y1="17" x2="12" y2="22" />
              <line x1="8" y1="22" x2="16" y2="22" />
            </svg>
          )}
        </button>

        <p className="mic-hint">
          {!isConnected ? 'Nhan de ket noi' :
            isConversationActive ? (
              isAiSpeaking ? 'Nhan de ngat loi AI' :
              isUserSpeaking ? 'Dang nghe ban noi...' :
              isListening ? 'Hay noi gi do...' :
              isProcessing ? 'Dang xu ly...' :
              'Cuoc tro chuyen dang hoat dong'
            ) :
            'Nhan de bat dau tro chuyen'}
        </p>

        {/* Stop conversation button (shown when active) */}
        {isConversationActive && (
          <button
            className="stop-conversation-btn"
            onClick={() => {
              if (isAiSpeaking) onInterrupt()
              onToggleConversation()
            }}
            title="Dung cuoc tro chuyen"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <rect x="4" y="4" width="16" height="16" rx="3" />
            </svg>
            Dung
          </button>
        )}
      </div>

      {/* Controls */}
      <div className="controls-row">
        <div className="control-group">
          <label>Giong noi</label>
          <select value={voice} onChange={e => onVoiceChange(e.target.value)}>
            <option value="female">Hoai My (Nu)</option>
            <option value="male">Nam Minh (Nam)</option>
          </select>
        </div>

        <button className="btn-clear" onClick={onClearMessages} title="Xoa lich su">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
          </svg>
          Xoa
        </button>
      </div>
    </div>
  )
}
