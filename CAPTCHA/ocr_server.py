import re
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import ddddocr
import uvicorn

app = FastAPI(title="Local ddddocr CAPTCHA Server")

# Initialize the OCR engine once when the server boots up
print("[*] Spawning local ddddocr neural network...")
ocr = ddddocr.DdddOcr(show_ad=False)


@app.post("/v1/decode-captcha")
async def decode_captcha(file: UploadFile = File(...)):
    """Receives binary image payloads and returns the parsed alphanumeric text sequence"""
    try:
        # Read the uploaded binary stream directly from memory
        image_bytes = await file.read()

        # Run classifications through the ddddocr engine
        raw_text = ocr.classification(image_bytes)

        # Strip spaces and punctuation artifacts
        cleaned_text = re.sub(r"\s+", "", raw_text).strip()

        print(f"[+] Decoded image buffer successfully: {cleaned_text}")
        return {"status": "success", "prediction": cleaned_text}

    except Exception as e:
        print(f"[!] Server processing error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Internal OCR processing error: {str(e)}"}
        )


if __name__ == "__main__":
    # Runs the local API server on http://127.0.0.1:8000
    uvicorn.run(app, host="127.0.0.1", port=8000)