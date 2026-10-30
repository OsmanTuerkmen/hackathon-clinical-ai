# Optional AI providers

AI stays off unless configured. Keep keys in `accessdesk2/.env` or in the process
environment; `.env` is git-ignored. Never commit or share the file.

```dotenv
ANTHROPIC_API_KEY=your-key
GEMINI_API_KEY=your-key
ELEVENLABS_API_KEY=your-key
```

## Gemini

Create a key in Google AI Studio using **Get API key**. Claude remains the
default when `ANTHROPIC_API_KEY` is present. Gemini is selected when
`GEMINI_API_KEY` is present without an Anthropic key, or explicitly with:

```dotenv
ACCESSDESK_AI_PROVIDER=gemini
```

The default model is `gemini-3.8-flash`; `ACCESSDESK_AI_MODEL` overrides it.
The current Google pricing page lists free input and output tokens for this
model on eligible free-tier projects, subject to model quota and rate limits.
Google notes that free-tier content may be used to improve its products; do not
send patient records or other sensitive material.

The REST implementation uses structured JSON output. The four prompts and
schemas remain in `accessdesk/ai_spec.py`; the application validates answers
afterward and can hold disagreements for staff review.

## ElevenLabs voiceover

Create a key from ElevenLabs **Profile → API keys**. The `--dry-run` command
does not need a key or make a network request:

```powershell
python tools/voiceover.py --dry-run
```

The documented premade Rachel voice (`21m00Tcm4TlvDq8ikWAM`) is the fallback
with `eleven_multilingual_v2`. Premade voices are English-origin and may retain
an English accent in German; use `python tools/voiceover.py --list-voices` to
inspect accessible voices, then select one explicitly:

```powershell
python tools/voiceover.py --voice <voice-id>
```

Restricted ElevenLabs keys need **Text to Speech: Access** for generation and
**Voices: Read** for `--list-voices`. The tool caches generated MP3 clips under
`docs/demo/voice/` by text, voice, model, and settings so reruns do not spend
credits again.

## Official documentation

Checked 2026-10-30:

- Gemini structured output: <https://ai.google.dev/gemini-api/docs/generate-content/structured-output>
- Gemini models: <https://ai.google.dev/gemini-api/docs/models>
- Gemini rate limits: <https://ai.google.dev/gemini-api/docs/rate-limits>
- Gemini pricing: <https://ai.google.dev/gemini-api/docs/pricing>
- Google AI Studio keys: <https://ai.google.dev/gemini-api/docs/api-key>
- ElevenLabs text-to-speech REST endpoint: <https://elevenlabs.io/docs/api-reference/text-to-speech/convert>
- ElevenLabs voice picker / premade voice ID: <https://ui.elevenlabs.io/docs/components/voice-picker>
