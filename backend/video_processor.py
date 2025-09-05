import os
import time
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
import yt_dlp
from langchain_ollama import OllamaLLM
from tqdm import tqdm
import numpy as np
import subprocess
import datetime
import re


class SimpleVideoToText:
    def __init__(self):
        print("🚀 Initializing Video to Text Converter")
        print("=" * 50)

        # Set environment variable to avoid potential issues
        os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

        ffmpeg_path = os.path.abspath("ffmpeg/bin")
        self.ffmpeg_path = ffmpeg_path
        self._check_ffmpeg_dependencies()

        with tqdm(total=100, desc="Loading speech model", bar_format="{l_bar}{bar}| {percentage:3.0f}%") as pbar:
            pbar.update(20)
            self.processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h")
            pbar.update(40)
            self.model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")
            pbar.update(30)
            self.llm = OllamaLLM(model="llama3.2", base_url="http://localhost:11434")
            pbar.update(10)

        print("✅ All models loaded successfully!")

    def _check_ffmpeg_dependencies(self):
        ffmpeg_exec = os.path.join(self.ffmpeg_path, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        ffprobe_exec = os.path.join(self.ffmpeg_path, "ffprobe.exe" if os.name == "nt" else "ffprobe")

        if not (os.path.exists(ffmpeg_exec) and os.path.exists(ffprobe_exec)):
            raise FileNotFoundError("❌ ffmpeg or ffprobe not found in 'ffmpeg/bin'. Please install FFmpeg correctly.")
        try:
            subprocess.check_output([ffmpeg_exec, "-version"], stderr=subprocess.DEVNULL)
            subprocess.check_output([ffprobe_exec, "-version"], stderr=subprocess.DEVNULL)
            print("✅ Local FFmpeg is working correctly")
        except Exception as e:
            raise EnvironmentError(f"❌ FFmpeg execution failed: {e}")

    def get_video_info(self, video_url):
        """Extract video title and ID for filename"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                title = info.get('title', 'Unknown_Video')
                video_id = info.get('id', 'unknown_id')

                # Clean title for filename
                title = re.sub(r'[<>:"/\\|?*]', '_', title)
                title = title[:50]  # Limit length

                return title, video_id
        except Exception as e:
            print(f"⚠️ Could not extract video info: {e}")
            return "Unknown_Video", "unknown_id"

    def download_audio(self, video_url):
        print("\n🎵 Downloading audio from video...")

        ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': 'temp_audio.%(ext)s',
    'quiet': True,
    # Only set ffmpeg_location if we have a local path
    **({'ffmpeg_location': self.ffmpeg_path} if self.ffmpeg_path else {}),
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'wav',
        'preferredquality': '192',
    }],
}
        audio_file = "temp_audio.wav"

        # Clean up any existing temp files
        for file in os.listdir('.'):
            if file.startswith('temp_audio'):
                try:
                    os.remove(file)
                except:
                    pass

        with tqdm(total=100, desc="Downloading audio", bar_format="{l_bar}{bar}| {percentage:3.0f}%") as pbar:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    print("🔄 Using yt-dlp with ffmpeg to extract .wav audio")
                    ydl.download([video_url])
                    pbar.update(100)
            except Exception as e:
                raise Exception(f"Audio download failed: {str(e)}")

        if not os.path.exists(audio_file):
            raise Exception("Audio file download or conversion failed")

        file_size = os.path.getsize(audio_file) / (1024 * 1024)
        print(f"✅ Audio ready: {audio_file} ({file_size:.1f} MB)")
        return audio_file

    def load_audio_simple(self, audio_file):
        print(f"🔍 Loading audio: {audio_file}")

        # Try soundfile first (more reliable)
        try:
            import soundfile as sf
            print("🔄 Using soundfile...")
            speech, rate = sf.read(audio_file)

            # Handle stereo audio
            if len(speech.shape) > 1:
                speech = speech.mean(axis=1)

            # Resample if needed using scipy instead of librosa
            if rate != 16000:
                from scipy import signal
                speech = signal.resample(speech, int(len(speech) * 16000 / rate))
                rate = 16000

            speech = speech.astype(np.float32)
            print(f"✅ Loaded {len(speech)} samples at {rate}Hz")
            return speech, rate

        except Exception as e:
            print(f"❌ Soundfile failed: {str(e)}")

        # Fallback to scipy.io.wavfile
        try:
            from scipy.io import wavfile
            print("🔄 Using scipy.io.wavfile...")
            rate, speech = wavfile.read(audio_file)

            # Convert to float32 and normalize
            if speech.dtype == np.int16:
                speech = speech.astype(np.float32) / 32768.0
            elif speech.dtype == np.int32:
                speech = speech.astype(np.float32) / 2147483648.0
            else:
                speech = speech.astype(np.float32)

            # Handle stereo
            if len(speech.shape) > 1:
                speech = speech.mean(axis=1)

            # Resample if needed
            if rate != 16000:
                from scipy import signal
                speech = signal.resample(speech, int(len(speech) * 16000 / rate))
                rate = 16000

            print(f"✅ Loaded {len(speech)} samples at {rate}Hz")
            return speech, rate

        except Exception as e:
            print(f"❌ Scipy failed: {str(e)}")

        # Final fallback - try librosa with error handling
        try:
            import librosa
            import warnings
            warnings.filterwarnings("ignore")

            print("🔄 Using librosa (fallback)...")
            speech, rate = librosa.load(audio_file, sr=16000)
            if len(speech) == 0:
                raise Exception("No audio data loaded")
            print(f"✅ Loaded {len(speech)} samples at {rate}Hz")
            return speech, rate
        except Exception as e:
            print(f"❌ Librosa failed: {str(e)}")
            raise Exception(f"Could not load {audio_file}. Please install: pip install soundfile scipy")

    def transcribe_audio(self, audio_file):
        print("\n🎤 Transcribing audio to text...")
        with tqdm(total=100, desc="Transcribing audio", bar_format="{l_bar}{bar}| {percentage:3.0f}%") as pbar:
            try:
                pbar.set_description("Loading audio file")
                speech, rate = self.load_audio_simple(audio_file)
                pbar.update(30)

                speech = speech.astype(np.float32)
                if np.max(np.abs(speech)) > 0:
                    speech = speech / np.max(np.abs(speech))

                print(f"🎵 Audio stats: {len(speech)} samples, range {speech.min():.3f} to {speech.max():.3f}")
                pbar.set_description("Preparing model input")
                inputs = self.processor(speech, sampling_rate=16000, return_tensors="pt")
                pbar.update(30)

                pbar.set_description("Running speech recognition")
                with torch.no_grad():
                    logits = self.model(inputs.input_values).logits
                pbar.update(30)

                predicted_ids = torch.argmax(logits, dim=-1)
                transcript = self.processor.decode(predicted_ids[0])
                transcript = transcript.strip()
                pbar.update(10)
            except Exception as e:
                raise Exception(f"Transcription failed: {str(e)}")

        if not transcript or len(transcript) < 3:
            transcript = "No clear speech detected in the audio."
        print(f"✅ Transcription complete: {len(transcript)} characters")
        return transcript

    def generate_summary(self, transcript):
        print("\n📝 Generating video summary...")

        prompt = f"""
        Please create a comprehensive summary of the following video transcript. 
        The summary should be medium to large in length, covering all main points, key insights, and important details discussed in the video.
        Make it informative and well-structured with clear sections and bullet points where appropriate.
        Include any important quotes, statistics, or examples mentioned.

        Transcript:
        {transcript}

        Summary:
        """

        with tqdm(total=100, desc="Generating summary", bar_format="{l_bar}{bar}| {percentage:3.0f}%") as pbar:
            pbar.update(20)
            summary = self.llm.invoke(prompt)
            pbar.update(80)

        return summary

    def save_transcript(self, transcript, video_title, video_id):
        """Save transcript to transcription folder"""
        os.makedirs("transcription", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{video_title}_{video_id}_{timestamp}.txt"
        filepath = os.path.join("transcription", filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("📄 VIDEO TRANSCRIPT\n")
            f.write("=" * 50 + "\n")
            f.write(f"Video Title: {video_title}\n")
            f.write(f"Video ID: {video_id}\n")
            f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            f.write(transcript)

        print(f"📁 Transcript saved to: {filepath}")
        return filepath

    def save_summary(self, summary, video_title, video_id):
        """Save summary to summaries folder"""
        os.makedirs("summaries", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{video_title}_{video_id}_{timestamp}.txt"
        filepath = os.path.join("summaries", filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("📝 VIDEO SUMMARY\n")
            f.write("=" * 50 + "\n")
            f.write(f"Video Title: {video_title}\n")
            f.write(f"Video ID: {video_id}\n")
            f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            f.write(summary)

        print(f"📁 Summary saved to: {filepath}")
        return filepath

    def process_video(self, video_url):
        start_time = time.time()
        try:
            print(f"🎯 Processing video: {video_url}")

            # Get video info for filename
            video_title, video_id = self.get_video_info(video_url)
            print(f"📹 Video: {video_title} (ID: {video_id})")

            print("\n" + "=" * 50)
            print("📥 STEP 1: DOWNLOADING AUDIO")
            print("=" * 50)
            audio_file = self.download_audio(video_url)

            print("\n" + "=" * 50)
            print("🔤 STEP 2: TRANSCRIBING AUDIO")
            print("=" * 50)
            transcript = self.transcribe_audio(audio_file)
            print(f"📝 Preview: {transcript[:150]}...")

            print("\n" + "=" * 50)
            print("📝 STEP 3: GENERATING SUMMARY")
            print("=" * 50)
            summary = self.generate_summary(transcript)

            print("\n" + "=" * 50)
            print("💾 STEP 4: SAVING FILES")
            print("=" * 50)

            # Save transcript and summary to files
            self.save_transcript(transcript, video_title, video_id)
            self.save_summary(summary, video_title, video_id)

            # Clean up temporary audio file
            if os.path.exists(audio_file):
                os.remove(audio_file)

            end_time = time.time()
            print(f"\n⏱️ Total processing time: {end_time - start_time:.2f} seconds")
            print("\n" + "=" * 60)
            print("🎉 PROCESSING COMPLETE!")
            print("=" * 60)
            print(f"\n📄 Transcript preview:\n{transcript[:200]}...\n")
            print(f"📝 Summary preview:\n{summary[:200]}...\n")
            print("✅ Files saved successfully!")
            print("\n📁 Check the following folders:")
            print("   - transcription/ (for full transcript)")
            print("   - summaries/ (for video summary)")
            
            return transcript, summary
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            # Clean up temporary audio files on error
            for file in os.listdir('.'):
                if file.startswith('temp_audio'):
                    try:
                        os.remove(file)
                    except:
                        pass
            return None, None


# Utility function for web app to validate video URL
def validate_video_url(video_input):
    """Validate and convert video input to proper URL"""
    if not video_input:
        return None
    
    video_input = video_input.strip()
    
    # Check if it's a full URL or just an ID
    if "youtube.com" in video_input or "youtu.be" in video_input:
        return video_input
    else:
        # Assume it's just the video ID
        return f"https://www.youtube.com/watch?v={video_input}"


# Global converter instance for web app (to avoid reloading models)
_converter_instance = None

def get_converter():
    """Get or create converter instance"""
    global _converter_instance
    if _converter_instance is None:
        _converter_instance = SimpleVideoToText()
    return _converter_instance