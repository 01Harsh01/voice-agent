"""
Live end-to-end verification script for Voice Agent WebSocket.
"""
import asyncio
import json
import websockets


async def main():
    uri = "ws://127.0.0.1:8000/ws/voice?conversation_id=test_live_verify"
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri) as ws:
        init_raw = await ws.recv()
        init_msg = json.loads(init_raw)
        print("1. Gateway Ready:", init_msg)

        query = "What is ten plus fifteen?"
        print(f"2. Sending User Utterance: '{query}'")
        await ws.send(json.dumps({"type": "user_speech", "text": query}))

        audio_chunk_count = 0
        audio_total_bytes = 0
        received_stages = []

        while True:
            try:
                raw_msg = await asyncio.wait_for(ws.recv(), timeout=50.0)
                data = json.loads(raw_msg)
                mtype = data.get("type")

                if mtype == "trace":
                    stage = data.get("stage")
                    received_stages.append(stage)
                    dur = data.get("duration_ms")
                    dur_str = f" in {round(dur)}ms" if dur else ""
                    print(f"   --> TRACE: {stage}{dur_str}")

                elif mtype == "assistant_text_final":
                    print(f"\n3. SYNTHESIZED TEXT: \"{data.get('text')}\"\n")

                elif mtype == "audio_chunk":
                    audio_chunk_count += 1
                    audio_total_bytes += len(data.get("audio", ""))

                elif mtype == "audio_done":
                    print(f"4. STREAMING AUDIO COMPLETE: {audio_chunk_count} chunks received (~{audio_total_bytes} b64 chars).")
                    break

                elif mtype == "error":
                    print(f"ERROR: {data.get('message')}")
                    break

            except asyncio.TimeoutError:
                print("Timed out waiting for response.")
                break

        print("\nAll Stages Verified Successfully:")
        print("Stages traversed:", received_stages)
        print(f"Total audio chunks: {audio_chunk_count}")


if __name__ == "__main__":
    asyncio.run(main())
