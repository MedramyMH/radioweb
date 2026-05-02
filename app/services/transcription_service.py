import os
from faster_whisper import WhisperModel

# On Railway, set MODEL_DIR to a persistent volume e.g., /app/models
MODEL_DIR = os.getenv("MODEL_DIR", "/tmp/whisper_models")
os.makedirs(MODEL_DIR, exist_ok=True)

model = None

def get_model():
    global model
    if model is None:
        # Using 'base' to save RAM/Railway limits. Change to 'small' or 'medium' if you have volume space.
        model = WhisperModel("base", device="cpu", compute_type="int8", download_root=MODEL_DIR)
    return model

def transcribe_audio(file_path: str, language: str = "en") -> list:
    model = get_model()
    segments, info = model.transcribe(file_path, language=language if language != "auto" else None)
    
    results = []
    for segment in segments:
        results.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text
        })
    return results