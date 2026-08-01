/**
 * Sprint 3 — Voice mode composable.
 *
 * Uses the browser's built-in Web Speech API (webkitSpeechRecognition
 * in Electron's Chromium). No external dependency needed.
 *
 * Usage:
 *   const { isListening, transcript, start, stop, speak } = useVoiceMode()
 *   start() begins recording, stop() returns the transcript
 *   speak(text) plays TTS via speechSynthesis
 */
import { ref, onUnmounted } from 'vue'

type SpeechRecognitionEvent = { results: { [k: number]: { [k: number]: { transcript: string } } } }

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: (e: SpeechRecognitionEvent) => void
  onerror: (e: unknown) => void
  onend: () => void
}

declare global {
  interface Window {
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
    SpeechRecognition?: new () => SpeechRecognitionLike
  }
}

export function useVoiceMode() {
  const isListening = ref(false)
  const transcript = ref('')
  const supported = ref(false)
  let recognition: SpeechRecognitionLike | null = null

  supported.value = typeof window !== 'undefined' &&
    (!!window.webkitSpeechRecognition || !!window.SpeechRecognition)

  function start() {
    if (!supported.value || isListening.value) return
    const Ctor = (window.webkitSpeechRecognition || window.SpeechRecognition)!
    recognition = new Ctor()
    recognition.lang = 'zh-CN'
    recognition.continuous = false
    recognition.interimResults = false
    recognition.onresult = (e) => {
      transcript.value = e.results[0]?.[0]?.transcript ?? ''
    }
    recognition.onerror = () => { isListening.value = false }
    recognition.onend = () => { isListening.value = false }
    recognition.start()
    isListening.value = true
  }

  function stop(): string {
    if (recognition) {
      recognition.stop()
      recognition = null
    }
    isListening.value = false
    return transcript.value
  }

  function speak(text: string) {
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    const u = new SpeechSynthesisUtterance(text)
    u.lang = 'zh-CN'
    u.rate = 1.1
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(u)
  }

  onUnmounted(() => { stop() })

  return { isListening, transcript, supported, start, stop, speak }
}
