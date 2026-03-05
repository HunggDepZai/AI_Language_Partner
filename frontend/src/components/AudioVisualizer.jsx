import React, { useRef, useEffect } from 'react'

export default function AudioVisualizer({ status, vadSpeaking, isConversationActive }) {
  const canvasRef = useRef(null)
  const animFrameRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const W = canvas.width = 240
    const H = canvas.height = 80

    let phase = 0

    const draw = () => {
      ctx.clearRect(0, 0, W, H)

      let amplitude, speed, color

      if (isConversationActive) {
        if (status === 'user_speaking' || vadSpeaking) {
          // User is speaking - big red waves
          amplitude = 30
          speed = 0.1
          color = '#ef4444'
        } else if (status === 'ai_speaking') {
          // AI is responding - blue waves
          amplitude = 22
          speed = 0.06
          color = '#3b82f6'
        } else if (status === 'processing') {
          // Processing - yellow pulse
          amplitude = 12
          speed = 0.04
          color = '#f59e0b'
        } else if (status === 'listening') {
          // Listening - subtle green breathing
          amplitude = 6 + Math.sin(phase * 0.3) * 3
          speed = 0.03
          color = '#10b981'
        } else {
          amplitude = 4
          speed = 0.02
          color = '#6b7280'
        }
      } else {
        amplitude = 4
        speed = 0.02
        color = '#6b7280'
      }

      phase += speed

      // Draw multiple sine waves
      for (let wave = 0; wave < 3; wave++) {
        ctx.beginPath()
        ctx.strokeStyle = color
        ctx.lineWidth = 2.5 - wave * 0.7
        ctx.globalAlpha = 1 - wave * 0.3

        for (let x = 0; x < W; x++) {
          const t = (x / W) * Math.PI * 4
          const y = H / 2 + Math.sin(t + phase + wave * 0.8) * amplitude * (1 - wave * 0.2) *
            Math.sin((x / W) * Math.PI)
          if (x === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.stroke()
      }

      // Draw center dot indicator when listening
      if (isConversationActive && status === 'listening' && !vadSpeaking) {
        const dotSize = 3 + Math.sin(phase * 2) * 1.5
        ctx.globalAlpha = 0.6
        ctx.fillStyle = color
        ctx.beginPath()
        ctx.arc(W / 2, H / 2, dotSize, 0, Math.PI * 2)
        ctx.fill()
      }

      ctx.globalAlpha = 1
      animFrameRef.current = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(animFrameRef.current)
  }, [status, vadSpeaking, isConversationActive])

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: '240px',
        height: '80px',
        display: 'block',
        margin: '0 auto',
      }}
    />
  )
}
