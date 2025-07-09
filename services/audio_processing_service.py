import os
import tempfile
import speech_recognition as sr
from pydub import AudioSegment
import io

class AudioProcessingService:
    def __init__(self):
        self.recognizer = sr.Recognizer()
    
    async def audio_to_text(self, audio_file: bytes, file_extension: str = "m4a") -> str:
        """
        Convert audio file bytes to text using speech recognition.
        
        Args:
            audio_file: Audio file as bytes
            file_extension: File extension (m4a, wav, mp3, etc.)
            
        Returns:
            Extracted text from the audio
        """
        try:
            # Create a temporary file to store the audio
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
                temp_file.write(audio_file)
                temp_file_path = temp_file.name
            
            # Convert audio to WAV format if needed (speech_recognition works best with WAV)
            if file_extension.lower() != "wav":
                audio = AudioSegment.from_file(temp_file_path, format=file_extension)
                wav_path = temp_file_path.replace(f".{file_extension}", ".wav")
                audio.export(wav_path, format="wav")
                temp_file_path = wav_path
            
            # Use speech recognition to convert audio to text
            with sr.AudioFile(temp_file_path) as source:
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = self.recognizer.record(source)
                
                # Perform speech recognition
                text = self.recognizer.recognize_google(audio_data)
                
                print(f"🎤 Audio converted to text: '{text}'")
                return text
                
        except sr.UnknownValueError:
            print("❌ Speech recognition could not understand the audio")
            raise Exception("Could not understand the audio. Please try speaking more clearly.")
            
        except sr.RequestError as e:
            print(f"❌ Speech recognition service error: {e}")
            raise Exception("Speech recognition service is currently unavailable.")
            
        except Exception as e:
            print(f"❌ Audio processing error: {e}")
            raise Exception(f"Failed to process audio: {str(e)}")
            
        finally:
            # Clean up temporary files
            try:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                if file_extension.lower() != "wav" and os.path.exists(temp_file_path.replace(".wav", f".{file_extension}")):
                    os.unlink(temp_file_path.replace(".wav", f".{file_extension}"))
            except:
                pass

# Global instance
audio_processing_service = AudioProcessingService() 