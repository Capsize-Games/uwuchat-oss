# Text-to-Speech

AI Runner supports multiple text-to-speech engines for voice output.

---

## Supported Engines

### OpenVoice
Advanced voice cloning TTS:
- High-quality voice synthesis
- Voice cloning from audio samples
- Multiple language support
- Download size: ~654 MB

**Configuration:**
- Set `AIRUNNER_ENABLE_OPEN_VOICE=1` to enable
- Provide a voice sample via `AIRUNNER_TTS_SPEAKER_RECORDING_PATH`

### SpeechT5
Microsoft's SpeechT5 model:
- Natural-sounding speech
- Multiple languages and accents
- Pitch, speed, and volume control

### eSpeak (Fallback)
Lightweight TTS engine:
- Fast, low-resource
- Multiple languages
- Pitch, speed, volume adjustment
- Installed via `sudo apt install espeak`

---

## Web UI Settings

TTS is configured in **Settings → TTS**:
- Voice selection
- Speed (words per minute)
- Pitch
- Volume

## API Usage

```bash
curl -X POST http://localhost:8188/tts/speak \
    -H "Content-Type: application/json" \
    -d '{"text": "Hello, this is a test", "voice": "default"}'
```
