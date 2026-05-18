import { useState, useEffect, useRef, useCallback } from 'react';
import { WakeWordEngine } from '../lib/WakeWordEngine.js';

/**
 * Hook wake word detection chạy 100% trên trình duyệt.
 * Sử dụng OpenWakeWord WASM + ONNX Runtime.
 */
export function useWakeword({ onDetect, keyword = 'hey_jarvis', threshold = 0.5 } = {}) {
    const [isLoaded, setIsLoaded] = useState(false);
    const [isListeningForWake, setIsListeningForWake] = useState(false);
    const [error, setError] = useState(null);
    const engineRef = useRef(null);
    const onDetectRef = useRef(onDetect);

    useEffect(() => { onDetectRef.current = onDetect; }, [onDetect]);

    // Init engine 1 lần
    useEffect(() => {
        const engine = new WakeWordEngine({
            baseAssetUrl: '/openwakeword/models',
            keywords: [keyword],
            detectionThreshold: threshold,
            cooldownMs: 2000,
            debug: false,
        });
        engineRef.current = engine;

        engine.on('detect', ({ keyword: kw, score }) => {
            console.log(`[WakeWord] Detected: ${kw} (score: ${score.toFixed(3)})`);
            if (onDetectRef.current) onDetectRef.current({ keyword: kw, score });
        });

        engine.on('error', (err) => {
            console.error('[WakeWord] Error:', err);
            setError(err?.message || String(err));
        });

        engine.load()
            .then(() => {
                console.log('[WakeWord] Models loaded successfully');
                setIsLoaded(true);
            })
            .catch(err => {
                console.error('[WakeWord] Load error:', err);
                setError(err?.message || String(err));
            });

        return () => {
            engine.stop();
        };
    }, [keyword, threshold]);

    const startListening = useCallback(async () => {
        if (!engineRef.current || !isLoaded) {
            console.warn('[WakeWord] Engine not loaded yet');
            return;
        }
        if (isListeningForWake) return;

        try {
            await engineRef.current.start();
            setIsListeningForWake(true);
            console.log('[WakeWord] Listening started');
        } catch (err) {
            console.error('[WakeWord] Start error:', err);
            setError(err?.message || String(err));
        }
    }, [isLoaded, isListeningForWake]);

    const stopListening = useCallback(() => {
        if (!engineRef.current) return;
        engineRef.current.stop();
        setIsListeningForWake(false);
        console.log('[WakeWord] Listening stopped');
    }, []);

    const toggleListening = useCallback(() => {
        if (isListeningForWake) {
            stopListening();
        } else {
            startListening();
        }
    }, [isListeningForWake, startListening, stopListening]);

    return { isLoaded, isListeningForWake, error, toggleListening, startListening, stopListening };
}
