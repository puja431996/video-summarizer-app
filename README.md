# Video Summarizer Application

A web application that summarizes video content from uploaded video files or YouTube links using AI-powered transcription and summarization.

## Features

- 📹 Upload video files (MP4, AVI, MOV, MKV, WEBM, FLV, WMV)
- 🔗 Process YouTube video links
- 🎤 Automatic speech-to-text transcription using OpenAI Whisper
- 📝 AI-powered text summarization
- 🎨 Modern, responsive web interface

## Prerequisites

- Python 3.8 or higher
- FFmpeg (required for video processing)

### Installing FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html and add to PATH

## Installation

1. Clone or navigate to the project directory:
```bash
cd /Users/pujakumari/Documents
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Set up OpenAI API key for enhanced summarization:
   - Create a `.env` file in the project directory
   - Add: `OPENAI_API_KEY=your_api_key_here`
   - If not set, the app will use a simple summarization method

## Usage

1. Start the Flask server:
```bash
python app.py
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

3. Choose one of the following options:
   - **YouTube Link**: Paste a YouTube video URL
   - **Upload Video**: Select a video file from your computer

4. (Optional) Check "Use OpenAI GPT for better summarization" if you have an OpenAI API key configured

5. Click "Generate Summary" and wait for the processing to complete

6. View the summary and full transcript

## How It Works

1. **Video Input**: Accepts either a YouTube URL or uploaded video file
2. **Video Processing**: Downloads YouTube videos or processes uploaded files
3. **Audio Extraction**: Extracts audio track from the video
4. **Transcription**: Uses OpenAI Whisper model to convert speech to text
5. **Summarization**: Generates a concise summary of the transcript
   - Uses OpenAI GPT-3.5-turbo if API key is configured
   - Falls back to simple summarization otherwise

## API Endpoints

- `GET /` - Serve the web interface
- `POST /api/summarize` - Process video and return summary
  - Body: FormData with `youtube_url` OR `video_file`, and optional `use_openai` flag
- `GET /api/health` - Health check endpoint

## Notes

- The first run will download the Whisper model (~150MB), which may take a few minutes
- Processing time depends on video length (typically 1-2 minutes per minute of video)
- Large video files may take longer to process
- Temporary files are automatically cleaned up after processing

## Troubleshooting

- **FFmpeg not found**: Make sure FFmpeg is installed and in your PATH
- **Model download issues**: Check your internet connection for the first run
- **Memory errors**: Try using a smaller Whisper model by changing `whisper.load_model("base")` to `whisper.load_model("tiny")` in app.py
- **YouTube download errors**: Some videos may be restricted or unavailable

## License

MIT License
