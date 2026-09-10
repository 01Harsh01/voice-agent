import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("RIME_API_KEY")

async def test():
    async with httpx.AsyncClient() as client:
        for fmt in ["mp3", "pcm", "wav"]:
            res = await client.post(
                "https://users.rime.ai/v1/rime-tts",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"speaker": "astra", "text": "Hello, this is a test.", "modelId": "coda", "audioFormat": fmt}
            )
            ct = res.headers.get("content-type")
            print(f"Format: {fmt} -> Status: {res.status_code}, Bytes: {len(res.content)}, Content-Type: {ct}")
            if len(res.content) > 0:
                print(f"  First 16 bytes: {list(res.content[:16])}")

asyncio.run(test())
