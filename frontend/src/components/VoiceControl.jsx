import React from 'react'

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
  onVoiceChange, onClearMessages,
  isListeningForWake, onToggleWake, isWakeLoaded
}) {

  const wakeButtonText = () => {
    if (!isWakeLoaded) return 'Dang tai mo hinh...'
    if (isListeningForWake) return '🎙️ Dang canh me: "Hey Jarvis"'
    return 'Bat goi Wakeword'
  }

  return (
    <div className="voice-control">
      {/* Mini Status Row */}
      <div className="status-bar" style={{ justifyContent: 'space-between', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="status-dot" style={{ backgroundColor: STATUS_COLOR[status] }} />
          <span className="status-text" style={{ fontSize: '11px' }}>{STATUS_TEXT[status]}</span>
        </div>
        {isConversationActive && <span className="mode-badge">LIVE</span>}
      </div>

      {/* Settings Row */}
      <div className="controls-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
        <button
          className="btn-wake"
          onClick={onToggleWake}
          disabled={!isWakeLoaded}
          style={{
            padding: '4px 8px', fontSize: '11px',
            background: isListeningForWake ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255,255,255,0.05)',
            color: isListeningForWake ? '#10b981' : 'white',
            border: `1px solid ${isListeningForWake ? '#10b981' : 'rgba(255,255,255,0.1)'}`,
            borderRadius: '4px', cursor: isWakeLoaded ? 'pointer' : 'wait',
            opacity: isWakeLoaded ? 1 : 0.6,
          }}
          title="Noi 'Hey Jarvis' de danh thuc AI"
        >
          {wakeButtonText()}
        </button>

        <div style={{ display: 'flex', gap: '8px' }}>
          <select
            value={voice}
            onChange={e => onVoiceChange(e.target.value)}
            style={{ padding: '2px 4px', fontSize: '11px', background: 'rgba(255,255,255,0.05)', color: 'white', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '4px' }}
          >
            <option value="female">Nu</option>
            <option value="male">Nam</option>
          </select>

          <button
            className="btn-clear"
            onClick={onClearMessages}
            style={{ padding: '2px 8px', fontSize: '11px', background: 'transparent' }}
          >
            Xoa
          </button>
        </div>
      </div>
    </div>
  )
}
