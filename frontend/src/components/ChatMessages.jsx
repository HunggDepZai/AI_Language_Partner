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
          <p className="empty-title">Xin chào! Tôi là Hướng dẫn viên du lịch Tiếng Việt</p>
          <p className="empty-subtitle">Hãy nói hoặc nhập câu hỏi của bạn về du lịch Việt Nam để bắt đầu cuộc trò chuyện!</p>
        </div>
      )}

      {messages.map((msg, i) => {
        const isSpeaking = msg.role === 'assistant' && currentAiText === '' && i === messages.length - 1;
        // Note: Simple heuristic for the very last message if it's AI
        return (
          <div key={i} className={`message message-${msg.role}`}>
            <div className="message-avatar">
              {msg.role === 'user' ? '👤' : '🤖'}
            </div>
            <div className="message-content">
              <div className="message-sender">
                {msg.role === 'user' ? 'Bạn' : 'Hướng dẫn viên AI'}
              </div>
              <div className={`message-text ${isSpeaking ? 'message-current-sentence' : ''}`}>
                {msg.text}
              </div>
            </div>
          </div>
        );
      })}

      {currentAiText && (
        <div className="message message-assistant">
          <div className="message-avatar">🤖</div>
          <div className="message-content message-current-sentence">
            <div className="message-sender">Trợ lý AI</div>
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
