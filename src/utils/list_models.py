import os
import google.generativeai as genai
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

def list_available_models():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not found.")
        return

    genai.configure(api_key=api_key)
    logger.info("Available models:")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            logger.info(f"- {m.name}")

if __name__ == "__main__":
    list_available_models()