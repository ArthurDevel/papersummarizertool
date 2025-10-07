"""
Simple hello world test for Hume AI Text-to-Speech API.

This script demonstrates basic TTS functionality by converting
a simple text message to speech and saving it as an MP3 file.
"""

import os
from pathlib import Path
from hume import HumeClient
from hume.tts import PostedUtterance, PostedUtteranceVoiceWithName, FormatMp3

from dotenv import load_dotenv

load_dotenv()

### CONSTANTS ###

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_FILENAME = "hello_world.mp3"


### MAIN FUNCTION ###

def synthesize_hello_world() -> None:
    """
    Synthesizes a simple 'Hello World' message to speech using Hume AI TTS.
    
    The function uses a preset voice from Hume's library and saves
    the resulting audio as an MP3 file in the output directory.
    
    Raises:
        ValueError: If HUME_API_KEY environment variable is not set
        Exception: If the TTS API call fails
    """
    # Step 1: Get API key from environment
    api_key = os.getenv("HUME_API_KEY")
    if not api_key:
        raise ValueError("HUME_API_KEY environment variable is not set")
    
    # Step 2: Initialize Hume client
    print("Initializing Hume AI client...")
    client = HumeClient(api_key=api_key)
    
    # Step 3: Define the text to synthesize
    text_to_speak = "Hello World! This is a test of the Hume AI text to speech system."
    print(f"Text to synthesize: {text_to_speak}")
    
    # Step 4: Synthesize speech with a preset voice
    print("Synthesizing speech...")
    audio_generator = client.tts.synthesize_file(
        utterances=[
            PostedUtterance(
                text=text_to_speak,
                voice=PostedUtteranceVoiceWithName(
                    name="Male English Actor",
                    provider="HUME_AI",
                ),
            )
        ],
        format=FormatMp3(),
    )
    
    # Step 5: Consume the generator to collect all audio bytes
    audio_chunks = []
    for chunk in audio_generator:
        audio_chunks.append(chunk)
    audio_data = b"".join(audio_chunks)
    
    # Step 6: Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 7: Save the audio to file
    output_path = OUTPUT_DIR / OUTPUT_FILENAME
    with open(output_path, "wb") as audio_file:
        audio_file.write(audio_data)
    
    print(f"Success! Audio saved to: {output_path}")
    print(f"File size: {len(audio_data)} bytes")


if __name__ == "__main__":
    try:
        synthesize_hello_world()
    except Exception as error:
        print(f"Error: {error}")
        raise

