# app.py - Hugging Face Spaces entry point
from app.main import app

# Hugging Face Spaces will automatically run this
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)