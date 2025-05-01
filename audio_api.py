# audio_api.py

from fastapi import FastAPI, Query
from google.cloud import texttospeech
from fastapi.responses import FileResponse
import uuid
import os

app = FastAPI()
tts_client = texttospeech.TextToSpeechClient()

AUDIO_DIR = "audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

@app.get("/generate-audio/")
async def generate_audio(text: str = Query(...)):
    filename = f"{uuid.uuid4()}.mp3"
    output_path = os.path.join(AUDIO_DIR, filename)

    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
    language_code="en-US",
    name="en-US-Wavenet-D",  # Exact male voice name
    ssml_gender=texttospeech.SsmlVoiceGender.MALE  # ← REQUIRED to force male
)   

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = tts_client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    with open(output_path, "wb") as out:
        out.write(response.audio_content)

    return FileResponse(output_path, media_type="audio/mpeg")
