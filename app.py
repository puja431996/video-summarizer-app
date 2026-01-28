import os
import tempfile
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import whisper
import yt_dlp
import imageio_ffmpeg
from moviepy.editor import VideoFileClip
import openai
from dotenv import load_dotenv

load_dotenv()

# Set FFmpeg path from imageio-ffmpeg (bundled with moviepy)
# This must be set before importing moviepy, but since we import it here,
# we'll set it and moviepy will use it automatically
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
os.environ['IMAGEIO_FFMPEG_EXE'] = ffmpeg_path

# Set up FFmpeg for Whisper - Whisper needs 'ffmpeg' command in PATH
ffmpeg_dir = os.path.dirname(ffmpeg_path)
current_path = os.environ.get('PATH', '')
if ffmpeg_dir not in current_path:
    os.environ['PATH'] = ffmpeg_dir + os.pathsep + current_path

# Create a symlink named 'ffmpeg' so Whisper can find it
# Whisper looks for 'ffmpeg' command, not the full path
import tempfile
temp_bin_dir = tempfile.mkdtemp()
ffmpeg_link = os.path.join(temp_bin_dir, 'ffmpeg')
if not os.path.exists(ffmpeg_link):
    try:
        os.symlink(ffmpeg_path, ffmpeg_link)
        os.environ['PATH'] = temp_bin_dir + os.pathsep + os.environ.get('PATH', '')
        print(f"Created ffmpeg symlink at {ffmpeg_link}")
    except Exception as e:
        print(f"Warning: Could not create ffmpeg symlink: {e}")

app = Flask(__name__)
CORS(app)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('temp', exist_ok=True)

# Initialize Whisper model (load once for better performance)
print("Loading Whisper model...")
whisper_model = whisper.load_model("base")
print("Whisper model loaded!")

# Optional: Set OpenAI API key if you want to use GPT for summarization
# openai.api_key = os.getenv("OPENAI_API_KEY")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def download_youtube_video(url):
    """Download YouTube video and return the file path"""
    temp_dir = tempfile.mkdtemp(dir='temp')
    
    # Try multiple strategies to avoid 403 errors
    strategies = [
        # Strategy 1: Download audio only (fastest, least likely to be blocked)
        {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                }
            },
        },
        # Strategy 2: Download video with android client
        {
            'format': 'best[height<=720]/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                }
            },
        },
        # Strategy 3: Download video with ios client
        {
            'format': 'best[height<=480]/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios'],
                }
            },
        },
        # Strategy 4: Download worst quality (most likely to work)
        {
            'format': 'worst',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        },
    ]
    
    common_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
    }
    
    last_error = None
    for i, strategy in enumerate(strategies):
        try:
            ydl_opts = {**common_opts, **strategy}
            print(f"Trying download strategy {i+1}...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                
                # If postprocessor was used, file extension might be different
                if 'postprocessors' in strategy:
                    # Audio was extracted, find the wav file
                    files = [f for f in os.listdir(temp_dir) if f.endswith('.wav')]
                    if files:
                        downloaded_file = os.path.join(temp_dir, files[0])
                    else:
                        # Fallback: find any audio file
                        audio_exts = ['.wav', '.m4a', '.mp3', '.opus']
                        for ext in audio_exts:
                            base_name = downloaded_file.rsplit('.', 1)[0]
                            if os.path.exists(base_name + ext):
                                downloaded_file = base_name + ext
                                break
                
                # Fix extension if needed
                if not os.path.exists(downloaded_file):
                    files = os.listdir(temp_dir)
                    if files:
                        downloaded_file = os.path.join(temp_dir, files[0])
                
                if os.path.exists(downloaded_file):
                    print(f"Successfully downloaded using strategy {i+1}")
                    return downloaded_file
                    
        except Exception as e:
            last_error = str(e)
            print(f"Strategy {i+1} failed: {last_error}")
            continue
    
    raise Exception(f"Error downloading YouTube video. All strategies failed. Last error: {last_error}. Please try again or upload the video file directly.")

def extract_audio(video_path):
    """Extract audio from video file"""
    try:
        # Ensure ffmpeg path is set for moviepy via imageio
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        os.environ['IMAGEIO_FFMPEG_EXE'] = ffmpeg_exe
        
        # MoviePy uses imageio-ffmpeg automatically, but we need to set it before importing
        # Since we already imported, we'll configure it via environment variable
        # MoviePy will pick it up from imageio_ffmpeg automatically
        
        video = VideoFileClip(video_path)
        audio_path = video_path.rsplit('.', 1)[0] + '_audio.wav'
        # write_audiofile doesn't accept ffmpeg_binary parameter, it uses imageio-ffmpeg automatically
        video.audio.write_audiofile(audio_path, verbose=False, logger=None)
        video.close()
        return audio_path
    except Exception as e:
        raise Exception(f"Error extracting audio: {str(e)}")

def transcribe_audio(audio_path):
    """Transcribe audio to text using Whisper"""
    try:
        # Ensure ffmpeg is available for Whisper
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        # Whisper uses ffmpeg via subprocess, so we need to ensure it's in PATH
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)
        current_path = os.environ.get('PATH', '')
        if ffmpeg_dir not in current_path:
            os.environ['PATH'] = ffmpeg_dir + os.pathsep + current_path
        
        # Also create a symlink named 'ffmpeg' in a temp directory that's in PATH
        # This ensures Whisper can find 'ffmpeg' command directly
        import tempfile
        temp_bin_dir = tempfile.mkdtemp()
        ffmpeg_link = os.path.join(temp_bin_dir, 'ffmpeg')
        
        # Create symlink if it doesn't exist
        if not os.path.exists(ffmpeg_link):
            try:
                os.symlink(ffmpeg_exe, ffmpeg_link)
                os.environ['PATH'] = temp_bin_dir + os.pathsep + os.environ.get('PATH', '')
            except Exception:
                # If symlink fails, just ensure the directory is in PATH
                pass
        
        result = whisper_model.transcribe(audio_path)
        return result["text"]
    except Exception as e:
        raise Exception(f"Error transcribing audio: {str(e)}")

def summarize_text(text, use_openai=False):
    """Summarize the transcribed text"""
    if use_openai and os.getenv("OPENAI_API_KEY"):
        try:
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes video transcripts concisely."},
                    {"role": "user", "content": f"Please provide a concise summary of the following video transcript:\n\n{text}"}
                ],
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI API error: {e}, falling back to simple summarization")
    
    # Simple summarization: return first few sentences and key points
    sentences = text.split('. ')
    if len(sentences) > 5:
        summary = '. '.join(sentences[:3]) + '.'
        summary += f"\n\nKey points:\n- " + "\n- ".join(sentences[3:8])
        return summary
    return text

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/summarize', methods=['POST'])
def summarize_video():
    try:
        # Handle both JSON and FormData requests
        if request.is_json:
            data = request.json
            youtube_url = data.get('youtube_url')
            video_file = None
            use_openai = data.get('use_openai', False)
        else:
            youtube_url = request.form.get('youtube_url')
            video_file = request.files.get('video_file')
            use_openai = request.form.get('use_openai', 'false').lower() == 'true'
        
        video_path = None
        temp_files = []
        
        # Handle YouTube URL
        audio_path = None
        if youtube_url:
            print(f"Downloading YouTube video: {youtube_url}")
            downloaded_file = download_youtube_video(youtube_url)
            temp_files.append(downloaded_file)
            temp_files.append(os.path.dirname(downloaded_file))
            
            # Check if audio was already extracted (wav, m4a, mp3, opus)
            audio_extensions = ['.wav', '.m4a', '.mp3', '.opus', '.ogg']
            file_ext = os.path.splitext(downloaded_file)[1].lower()
            if file_ext in audio_extensions:
                print("Audio already extracted from YouTube")
                audio_path = downloaded_file
                video_path = None  # No video to extract from
            else:
                video_path = downloaded_file
        
        # Handle uploaded video file
        elif video_file and video_file.filename:
            if not allowed_file(video_file.filename):
                return jsonify({'error': 'Invalid file type. Allowed types: mp4, avi, mov, mkv, webm, flv, wmv'}), 400
            
            video_path = os.path.join(UPLOAD_FOLDER, video_file.filename)
            video_file.save(video_path)
            temp_files.append(video_path)
        
        else:
            return jsonify({'error': 'Please provide either a YouTube URL or upload a video file'}), 400
        
        # Extract audio if not already extracted
        if not audio_path:
            print("Extracting audio from video...")
            audio_path = extract_audio(video_path)
            temp_files.append(audio_path)
        
        # Transcribe audio
        print("Transcribing audio...")
        transcript = transcribe_audio(audio_path)
        
        # Summarize text
        print("Summarizing text...")
        summary = summarize_text(transcript, use_openai=use_openai)
        
        # Clean up temporary files
        for file_path in temp_files:
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    import shutil
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Warning: Could not delete {file_path}: {e}")
        
        return jsonify({
            'success': True,
            'transcript': transcript,
            'summary': summary
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
