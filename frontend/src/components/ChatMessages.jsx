import React, { useRef, useEffect } from 'react'

export default function ChatMessages({ messages, currentAiText }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentAiText])

  return (
    <div className="chat-messages">
      {messages.length === 0 && !currentAiText && (
        <div className="empty-state">
          <div className="empty-icon">🎙️</div>
          <p className="empty-title">Xin chao! Toi la tro ly AI tieng Viet</p>
          <p className="empty-subtitle">
            Nhan nut ben duoi de bat dau tro chuyen tu do.
            <br />
            <span className="empty-feature">AI tu dong nghe va tra loi - khong can giu nut!</span>
          </p>
        </div>
      )}

      {messages.map((msg, i) => (
        <div key={i} className={`message message-${msg.role}`}>
          <div className="message-avatar">
            {msg.role === 'user' ? '👤' : '🤖'}
          </div>
          <div className="message-content">
            <div className="message-sender">
              {msg.role === 'user' ? 'Ban' : 'Tro ly AI'}
            </div>
            <div className="message-text">{msg.text}</div>
          </div>
        </div>
      ))}

      {currentAiText && (
        <div className="message message-assistant">
          <div className="message-avatar">🤖</div>
          <div className="message-content">
            <div className="message-sender">Tro ly AI</div>
            <div className="message-text">
              {currentAiText}
              <span className="typing-cursor">▌</span>
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
