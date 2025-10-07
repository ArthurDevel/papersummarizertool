# Hume AI Text-to-Speech Test Script

This directory contains test scripts for exploring the Hume AI Text-to-Speech (TTS) API.

## Setup Instructions

### 1. Create and Activate Virtual Environment

It is recommended to use a virtual environment to avoid package conflicts.

```bash
cd testscripts/2025.10.07-test-hume-tts
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install hume python-dotenv
```

### 3. Set API Key

Get your API key from [Hume AI](https://platform.hume.ai/) and set it using one of these methods:

**Option 1: Using a .env file (recommended)**

Create a `.env` file in this directory:

```bash
echo 'HUME_API_KEY=your_api_key_here' > .env
```

**Option 2: Using an environment variable**

```bash
export HUME_API_KEY="your_api_key_here"
```

Or add it to your shell profile (`.bashrc`, `.zshrc`, etc.):

```bash
echo 'export HUME_API_KEY="your_api_key_here"' >> ~/.zshrc
source ~/.zshrc
```

## Running the Scripts

### 1. Hello World Example

Synthesizes a simple "Hello World" message to speech:

```bash
python 1-hello-world.py
```

Output will be saved to `output/hello_world.mp3`

### 2. Podcast from Paper

Interactive script to generate a podcast from a paper in the database:

```bash
python 2-podcast-from-paper.py
```

This script will:
1. Connect to the database
2. List all completed papers
3. Allow you to select a paper interactively
4. Generate a podcast from the selected paper (coming soon)

## Script Descriptions

- **1-hello-world.py**: Basic example that converts a simple text message to speech using a preset voice from Hume's library
- **2-podcast-from-paper.py**: Interactive script to select a paper from the database and generate a podcast from it

## Output Files

All generated audio files are saved to the `output/` directory.

## Hume AI TTS Features

The Hume AI TTS API provides:

- Multiple preset voices from Hume's Voice Library
- Custom voice creation and saving
- Dynamic voice generation based on text descriptions
- Context support for consistent speech style across requests
- Multiple audio format options (MP3, WAV, etc.)
- Streaming support for real-time applications

## Documentation

For more information, visit:
- [Hume AI Documentation](https://dev.hume.ai/)
- [Hume Python SDK](https://github.com/humeai/hume-python-sdk)

