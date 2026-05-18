import React, { useRef, useEffect } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

export default function VrmViewer({ analyser, status }) {
    const containerRef = useRef(null);
    const avatarRef = useRef(null);
    const mixerRef = useRef(null);
    const morphRef = useRef({});
    const analyserNodeRef = useRef(null);
    const requestRef = useRef();

    // Cập nhật analyser ref khi nó thay đổi mà không cần khởi tạo lại scene
    useEffect(() => {
        analyserNodeRef.current = analyser;
    }, [analyser]);

    useEffect(() => {
        let clock = new THREE.Clock();
        let renderer, scene, camera;
        let isDisposed = false;

        const init = async () => {
            console.log('[VRM] Khởi tạo scene...');

            // ── Thiết lập Scene ──
            scene = new THREE.Scene();

            camera = new THREE.PerspectiveCamera(35, window.innerWidth / window.innerHeight, 0.1, 100);
            camera.position.set(0, 8.5, 6);

            renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

            if (containerRef.current) {
                containerRef.current.innerHTML = ''; // Đảm bảo container trống trước khi thêm canvas mới
                containerRef.current.appendChild(renderer.domElement);
            }

            const ambientLight = new THREE.AmbientLight(0xffffff, 1.0);
            scene.add(ambientLight);

            const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight.position.set(1, 2, 3);
            scene.add(directionalLight);

            // ── Tải Cấu hình & Model ──
            try {
                console.log('[VRM] Đang tải bot_config...');
                let botConfig = null;
                try {
                    const configResp = await fetch('/static/bot_config.json');
                    if (configResp.ok) botConfig = await configResp.json();
                } catch (e) {
                    console.warn('[VRM] Không thể tải bot_config, sử dụng mặc định.');
                }

                const loader = new GLTFLoader();
                let modelUrl = '/static/model.glb';
                if (botConfig?.modelInfo?.name) {
                    modelUrl = `/static/${botConfig.modelInfo.name}.glb`;
                }

                console.log('[VRM] Đang tải model từ:', modelUrl);
                loader.load(
                    modelUrl,
                    (gltf) => {
                        if (isDisposed) return;
                        console.log('[VRM] Model đã tải xong');
                        const avatar = gltf.scene;
                        avatarRef.current = avatar;
                        scene.add(avatar);

                        // Lấy Morph Targets
                        const dict = {};
                        console.log('[VRM] Full list of nodes in model:');
                        avatar.traverse((child) => {
                            if (child.isMesh) {
                                console.log(` - Mesh found: ${child.name}`, child.morphTargetDictionary);
                                if (child.morphTargetDictionary) {
                                    Object.assign(dict, child.morphTargetDictionary);
                                }
                            }
                        });
                        morphRef.current = dict;
                        console.log('[VRM] Combined Morph Targets dictionary:', dict);

                        // Animation
                        if (gltf.animations && gltf.animations.length > 0) {
                            const mixer = new THREE.AnimationMixer(avatar);
                            mixerRef.current = mixer;
                            const idx = botConfig?.currentState?.animationIndex ?? 0;
                            const action = mixer.clipAction(gltf.animations[idx]);
                            action.play();
                        }
                    },
                    (progress) => {
                        const percent = (progress.loaded / progress.total * 100).toFixed(0);
                        if (percent % 25 === 0) console.log(`[VRM] Tiến độ tải: ${percent}%`);
                    },
                    (error) => {
                        console.error('[VRM] Lỗi khi tải model:', error);
                    }
                );
            } catch (err) {
                console.error('[VRM] Lỗi khởi tạo chung:', err);
            }

            // Xử lý Resize
            const handleResize = () => {
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            };
            window.addEventListener('resize', handleResize);

            // ── Biến nội bộ cho vòng lặp ──
            let mouthOpenValue = 0;
            let blinkTimer = 0;
            let blinkInterval = 3;
            const vowels = ['Fcl_MTH_A', 'Fcl_MTH_I', 'Fcl_MTH_U', 'Fcl_MTH_E', 'Fcl_MTH_O'];
            let currentVowel = 'Fcl_MTH_A';
            let vowelChangeTimer = 0;
            const dataArray = new Uint8Array(128);

            const setMorph = (name, value) => {
                // Thử các chuẩn đặt tên khác nhau cho Morph Target
                const variations = [
                    name,
                    name.replace('Fcl_MTH_', 'VISE_'), // VISE_A
                    name.replace('Fcl_MTH_', ''),      // A
                    `Mth_${name.replace('Fcl_MTH_', '')}` // Mth_A
                ];

                let index = undefined;
                for (const v of variations) {
                    if (morphRef.current[v] !== undefined) {
                        index = morphRef.current[v];
                        break;
                    }
                }

                if (index === undefined || !avatarRef.current) return;
                avatarRef.current.traverse((child) => {
                    if (child.isMesh && child.morphTargetInfluences && index < child.morphTargetInfluences.length) {
                        child.morphTargetInfluences[index] = Math.max(0, Math.min(1, value));
                    }
                });
            };

            const animate = () => {
                if (isDisposed) return;
                const delta = clock.getDelta();
                if (mixerRef.current) mixerRef.current.update(delta);

                // Lip Sync - Đồng bộ hoàn toàn với cơ chế bản Web
                if (analyserNodeRef.current) {
                    analyserNodeRef.current.getByteFrequencyData(dataArray);
                    let sum = 0;
                    for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                    let average = sum / dataArray.length;

                    // Debug (có thể bỏ log này sau khi đã chạy ổn)
                    // if (average > 1) console.log(`[VRM] Audio Level: ${average.toFixed(2)}`);

                    let targetOpen = Math.min(average / 35, 1.1); // Độ nhạy trung bình như bản web
                    mouthOpenValue = THREE.MathUtils.lerp(mouthOpenValue, targetOpen, 0.4);

                    vowels.forEach(v => setMorph(v, 0)); // Reset trước khi set mới

                    if (mouthOpenValue > 0.05) { // Ngưỡng nhỏ hơn để nhạy hơn
                        if (vowelChangeTimer > 8) {
                            currentVowel = vowels[Math.floor(Math.random() * vowels.length)];
                            vowelChangeTimer = 0;
                        }
                        vowelChangeTimer++;

                        setMorph(currentVowel, mouthOpenValue);
                        if (currentVowel !== 'Fcl_MTH_O') setMorph('Fcl_MTH_U', mouthOpenValue * 0.2);
                    } else {
                        mouthOpenValue = 0;
                    }
                }


                // Auto Blink
                blinkTimer += delta;
                if (blinkTimer >= blinkInterval) {
                    let blinkDuration = 0.15;
                    let timeInBlink = blinkTimer - blinkInterval;
                    if (timeInBlink <= blinkDuration) {
                        let progress = Math.sin((timeInBlink / blinkDuration) * Math.PI);
                        setMorph('Fcl_EYE_Close', progress);
                    } else {
                        setMorph('Fcl_EYE_Close', 0);
                        blinkTimer = 0;
                        blinkInterval = 2 + Math.random() * 5;
                    }
                }

                renderer.render(scene, camera);
                requestRef.current = requestAnimationFrame(animate);
            };

            animate();

            return () => {
                console.log('[VRM] Đang dọn dẹp...');
                isDisposed = true;
                window.removeEventListener('resize', handleResize);
                cancelAnimationFrame(requestRef.current);
                if (renderer) {
                    renderer.dispose();
                    if (containerRef.current && renderer.domElement.parentNode === containerRef.current) {
                        containerRef.current.removeChild(renderer.domElement);
                    }
                }
            };
        };

        const cleanupFnPromise = init();
        return () => {
            cleanupFnPromise.then(cleanup => cleanup && cleanup());
        };
    }, []); // Chỉ chạy một lần khi mount

    return (
        <div
            ref={containerRef}
            id="vrm-container"
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                width: '100vw',
                height: '100vh',
                zIndex: 0, // Đặt đằng sau UI
                pointerEvents: 'none',
                background: 'transparent'
            }}
        />
    );
}
