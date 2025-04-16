import asyncio
import json
import time
import cv2
import numpy as np
import pyautogui
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame


class ScreenCaptureTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.fps = 15
        self.last_capture = time.time()

    async def recv(self):
        current_time = time.time()
        if current_time - self.last_capture < 1 / self.fps:
            await asyncio.sleep(1 / self.fps - (current_time - self.last_capture))
        self.last_capture = time.time()

        img = pyautogui.screenshot()
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        frame = cv2.resize(frame, (1280, 720))

        pts, time_base = await self.next_timestamp()

        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame


pcs = set()


async def index(request):
    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()
    return web.Response(content_type="text/html", text=content)


async def offer(request):
    params = await request.json()
    _offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState in ("failed", "closed"):
            await pc.close()
            pcs.discard(pc)

    screen_track = ScreenCaptureTrack()
    pc.addTrack(screen_track)

    await pc.setRemoteDescription(_offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


async def main():
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)

    print("Iniciando servidor em http://localhost:8080")
    return app


if __name__ == "__main__":
    web.run_app(main(), host="0.0.0.0", port=8080)
