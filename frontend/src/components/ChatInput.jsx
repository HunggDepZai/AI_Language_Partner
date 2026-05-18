import React, { useState } from 'react';

export default function ChatInput({
    onSendMessage,
    disabled,
    isConnected,
    isConversationActive,
    status,
    onConnect,
    onToggleConversation,
    onInterrupt
}) {
    const [text, setText] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        if (text.trim() && !disabled) {
            onSendMessage(text.trim());
            setText('');
        }
    };

    const handleMicClick = () => {
        if (!isConnected) {
            onConnect();
            return;
        }
        if (status === 'ai_speaking' && isConversationActive) {
            onInterrupt();
            return;
        }
        onToggleConversation();
    };

    const isListening = status === 'listening';
    const isUserSpeaking = status === 'user_speaking';
    const isAiSpeaking = status === 'ai_speaking';
    const isProcessing = status === 'processing';
    const isBusy = isProcessing || isAiSpeaking;

    return (
        <div className="chat-input-wrapper">
            <form className="chat-input-container" onSubmit={handleSubmit}>
                <input
                    type="text"
                    className="chat-input"
                    placeholder="Gửi tin nhắn..."
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    disabled={disabled}
                />

                <div className="chat-input-actions">
                    {/* Nút Mic thông minh */}
                    <button
                        type="button"
                        className={`mini-mic-btn ${isConversationActive ? (isUserSpeaking ? 'active-speaking' : isAiSpeaking ? 'active-ai' : isListening ? 'active-listening' : 'active-on') : ''}`}
                        onClick={handleMicClick}
                        title={isConnected ? (isConversationActive ? 'Dừng hội thoại' : 'Bắt đầu hội thoại') : 'Kết nối để bắt đầu'}
                    >
                        {!isConnected ? (
                            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5">
                                <path d="M5 12h14M12 5l7 7-7 7" />
                            </svg>
                        ) : isConversationActive ? (
                            isAiSpeaking ? (
                                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                                    <rect x="6" y="4" width="4" height="16" />
                                    <rect x="14" y="4" width="4" height="16" />
                                </svg>
                            ) : (
                                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                                    <rect x="3" y="10" width="3" height="4"><animate attributeName="height" values="4;12;4" dur="0.8s" repeatCount="indefinite" /></rect>
                                    <rect x="8" y="7" width="3" height="10"><animate attributeName="height" values="10;4;10" dur="0.6s" repeatCount="indefinite" /></rect>
                                    <rect x="13" y="5" width="3" height="14"><animate attributeName="height" values="14;8;14" dur="0.7s" repeatCount="indefinite" /></rect>
                                    <rect x="18" y="10" width="3" height="4"><animate attributeName="height" values="4;12;4" dur="0.9s" repeatCount="indefinite" /></rect>
                                </svg>
                            )
                        ) : (
                            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5">
                                <rect x="9" y="2" width="6" height="12" rx="3" />
                                <path d="M5 10a7 7 0 0 0 14 0M12 17v5" />
                            </svg>
                        )}
                    </button>

                    {/* Nút Gửi tin nhắn */}
                    <button
                        type="submit"
                        className="chat-send-btn"
                        disabled={!text.trim() || disabled}
                    >
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <line x1="22" y1="2" x2="11" y2="13" />
                            <polygon points="22 2 15 22 11 13 2 9 22 2" />
                        </svg>
                    </button>
                </div>
            </form>
        </div>
    );
}
