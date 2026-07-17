"""Headless Chromium bridge for Google SDM WebRTC camera streams."""

import asyncio
import glob
import json
import os
import secrets
import shutil
import socket
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin


PAGE = r"""<!doctype html>
<meta charset="utf-8">
<title>Nest WebRTC bridge</title>
<video id="video" autoplay playsinline muted></video>
<script>
const base = location.pathname.replace(/\/$/, '');
const video = document.querySelector('#video');
const source = new RTCPeerConnection();
const stream = new MediaStream();
let publisher = null;
let reporting = false;
video.srcObject = stream;

source.ontrack = event => {
  stream.addTrack(event.track);
  video.play().catch(() => {});
};

async function gather(peer) {
  if (peer.iceGatheringState === 'complete') return;
  await new Promise(resolve => {
    const changed = () => {
      if (peer.iceGatheringState === 'complete') {
        peer.removeEventListener('icegatheringstatechange', changed);
        resolve();
      }
    };
    peer.addEventListener('icegatheringstatechange', changed);
  });
}

async function request(path, options) {
  const response = await fetch(base + path, options);
  const text = await response.text();
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${text}`);
  return text;
}

async function report() {
  if (reporting) return;
  reporting = true;
  try {
    const inbound = [];
    for (const item of (await source.getStats()).values()) {
      if (item.type === 'inbound-rtp') {
        inbound.push({
          kind: item.kind,
          packets: item.packetsReceived || 0,
          bytes: item.bytesReceived || 0,
          framesDecoded: item.framesDecoded || 0,
          framesDropped: item.framesDropped || 0,
        });
      }
    }
    await fetch(base + '/status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        sourceState: source.connectionState,
        publisherState: publisher ? publisher.connectionState : 'not-created',
        inbound,
      }),
    });
  } finally {
    reporting = false;
  }
}

async function fail(error) {
  try {
    await fetch(base + '/error', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({error: String(error && (error.stack || error))}),
    });
  } catch (_) {}
}

async function start() {
  // Google requires audio, video, and application m-lines in this order.
  source.addTransceiver('audio', {direction: 'recvonly'});
  source.addTransceiver('video', {direction: 'recvonly'});
  source.createDataChannel('nest-control');
  await source.setLocalDescription(await source.createOffer());
  await gather(source);
  const answerText = await request('/offer', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sdp: source.localDescription.sdp}),
  });
  const answer = JSON.parse(answerText);
  await source.setRemoteDescription({type: 'answer', sdp: answer.sdp});

  const trackDeadline = Date.now() + 15000;
  while (stream.getVideoTracks().length === 0 && Date.now() < trackDeadline) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (stream.getVideoTracks().length === 0) throw new Error('No Google video track');

  publisher = new RTCPeerConnection();
  for (const track of stream.getTracks()) {
    const sender = publisher.addTrack(track, stream);
    const transceiver = publisher.getTransceivers().find(t => t.sender === sender);
    const wanted = track.kind === 'video' ? 'video/H264' : 'audio/opus';
    const codecs = RTCRtpSender.getCapabilities(track.kind).codecs.filter(
      codec => codec.mimeType.toLowerCase() === wanted.toLowerCase()
    );
    if (!codecs.length) throw new Error(`Chromium does not provide ${wanted}`);
    transceiver.setCodecPreferences(codecs);
  }
  await publisher.setLocalDescription(await publisher.createOffer());
  await gather(publisher);
  const whipAnswer = await request('/whip', {
    method: 'POST',
    headers: {'Content-Type': 'application/sdp'},
    body: publisher.localDescription.sdp,
  });
  await publisher.setRemoteDescription({type: 'answer', sdp: whipAnswer});
  await report();
  setInterval(report, 1000);
}

window.addEventListener('error', event => fail(event.error || event.message));
window.addEventListener('unhandledrejection', event => fail(event.reason));
start().catch(fail);
</script>
"""


def find_chromium_executable(configured_path=""):
    """Return an installed Chrome/Chromium executable or raise a useful error."""
    requested = configured_path or os.environ.get(
        "NEST_WEBRTC_BROWSER_EXECUTABLE", ""
    )
    if requested:
        executable = Path(os.path.expanduser(requested))
        if executable.is_file() and os.access(executable, os.X_OK):
            return str(executable)
        raise RuntimeError(f"Configured Chromium executable is unusable: {executable}")

    for command in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        executable = shutil.which(command)
        if executable:
            return executable

    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    ]
    cache = os.path.expanduser("~/Library/Caches/ms-playwright")
    candidates.extend(
        glob.glob(
            os.path.join(
                cache,
                "chromium-*",
                "chrome-mac-*",
                "Google Chrome for Testing.app",
                "Contents",
                "MacOS",
                "Google Chrome for Testing",
            )
        )
    )
    candidates.extend(
        glob.glob(
            os.path.join(
                cache,
                "chromium_headless_shell-*",
                "chrome-headless-shell-mac-*",
                "chrome-headless-shell",
            )
        )
    )
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise RuntimeError(
        "No Chromium executable was found. Install one with "
        "`python -m playwright install chromium` or configure "
        "RTSP_SERVER.webrtc_browser_executable."
    )


class BrowserWebRTCSession:
    """Receive one Nest camera in Chromium and republish it through WHIP."""

    def __init__(self, camera):
        self.camera = camera
        self.logger = camera._logger
        self.http = None
        self.runner = None
        self.browser = None
        self.profile = None
        self.socket = None
        self.media_session_id = None
        self.whip_resource_url = None
        self.ready = asyncio.Event()
        self.failure = None
        self.last_status = time.monotonic()
        self.last_frames = 0
        self.token = secrets.token_urlsafe(24)

    def _route(self, suffix=""):
        return f"/{self.token}{suffix}"

    async def _page(self, _request):
        return self._web.Response(text=PAGE, content_type="text/html")

    async def _offer(self, request):
        try:
            payload = await request.json()
            response = await self.camera._send_command_async(
                "CameraLiveStream.GenerateWebRtcStream",
                {"offerSdp": payload["sdp"]},
            )
            results = response["results"]
            self.media_session_id = results["mediaSessionId"]
            self.camera._media_session_id = self.media_session_id
            self.camera._record_expiration(
                results["expiresAt"], "Started Chromium WebRTC session"
            )
            answer, count = self.camera._normalize_google_answer_sdp(
                results["answerSdp"]
            )
            if count:
                self.logger.warning(
                    "Normalized %d Google ICE candidate(s) missing a component ID",
                    count,
                )
            self.logger.info(
                "Google answer SDP media: %s",
                self.camera._summarize_sdp_media(answer),
            )
            return self._web.json_response({"sdp": answer})
        except Exception as error:
            self.failure = error
            self.logger.error("Chromium offer failed: %r", error)
            return self._web.json_response({"error": repr(error)}, status=500)

    async def _whip(self, request):
        try:
            publish_url = self.camera._webrtc_publish_url()
            offer = await request.text()
            auth = self.camera._webrtc_publish_auth(self._aiohttp)
            async with self.http.post(
                publish_url,
                data=offer,
                headers={"Content-Type": "application/sdp"},
                auth=auth,
            ) as response:
                answer = await response.text()
                if response.status not in (200, 201):
                    raise RuntimeError(
                        f"MediaMTX WHIP POST returned {response.status}: {answer[:500]}"
                    )
                location = response.headers.get("Location")
                if location:
                    self.whip_resource_url = urljoin(publish_url, location)
                return self._web.Response(text=answer, content_type="application/sdp")
        except Exception as error:
            self.failure = error
            self.logger.error("Chromium WHIP publishing failed: %r", error)
            return self._web.Response(text=repr(error), status=500)

    async def _status(self, request):
        status = await request.json()
        self.last_status = time.monotonic()
        video = next(
            (
                item
                for item in status.get("inbound", [])
                if item.get("kind") == "video"
            ),
            {},
        )
        frames = int(video.get("framesDecoded", 0) or 0)
        if (
            frames > 0
            and status.get("sourceState") == "connected"
            and status.get("publisherState") == "connected"
        ):
            self.last_frames = frames
            if not self.ready.is_set():
                self.logger.warning(
                    "Chromium decoded Google video and published it to MediaMTX "
                    "(%d frames, %d dropped)",
                    frames,
                    int(video.get("framesDropped", 0) or 0),
                )
                self.ready.set()
        if status.get("sourceState") in ("failed", "closed"):
            self.failure = RuntimeError(
                f"Google Chromium WebRTC connection is {status['sourceState']}"
            )
        if status.get("publisherState") in ("failed", "closed"):
            self.failure = RuntimeError(
                f"MediaMTX Chromium connection is {status['publisherState']}"
            )
        return self._web.Response(status=204)

    async def _error(self, request):
        payload = await request.json()
        self.failure = RuntimeError(
            f"Chromium bridge page failed: {payload.get('error', 'unknown error')}"
        )
        return self._web.Response(status=204)

    async def _start_server(self):
        import aiohttp
        from aiohttp import web

        self._aiohttp = aiohttp
        self._web = web
        self.http = aiohttp.ClientSession()
        app = web.Application(client_max_size=1024 * 1024)
        app.router.add_get(self._route("/"), self._page)
        app.router.add_post(self._route("/offer"), self._offer)
        app.router.add_post(self._route("/whip"), self._whip)
        app.router.add_post(self._route("/status"), self._status)
        app.router.add_post(self._route("/error"), self._error)
        # Status is posted once per second; keep it out of normal verbose logs.
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(128)
        self.socket.setblocking(False)
        site = web.SockSite(self.runner, self.socket)
        await site.start()
        return self.socket.getsockname()[1]

    async def _start_browser(self, port):
        configured = self.camera._configuration.get(
            "RTSP_SERVER", "webrtc_browser_executable", fallback=""
        )
        executable = find_chromium_executable(configured)
        self.profile = tempfile.TemporaryDirectory(
            prefix=f"nest-{self.camera.legal_camera_name}-"
        )
        headless = self.camera._configuration.getboolean(
            "RTSP_SERVER", "webrtc_browser_headless", fallback=True
        )
        arguments = [
            executable,
            "--autoplay-policy=no-user-gesture-required",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-extensions",
            "--no-default-browser-check",
            "--no-first-run",
            f"--user-data-dir={self.profile.name}",
        ]
        if headless:
            arguments.append("--headless=new")
        arguments.append(f"http://127.0.0.1:{port}{self._route('/')}")
        self.logger.info("Starting %s Chromium WebRTC worker", "headless" if headless else "visible")
        self.browser = await asyncio.create_subprocess_exec(
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def _wait_until_ready(self):
        deadline = time.monotonic() + self.camera._webrtc_video_start_timeout
        while not self.ready.is_set():
            if self.failure is not None:
                raise self.failure
            if self.browser.returncode is not None:
                raise RuntimeError(
                    f"Chromium exited before publishing (status {self.browser.returncode})"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Chromium did not decode and publish Google video within "
                    f"{self.camera._webrtc_video_start_timeout:.0f} seconds"
                )
            await asyncio.sleep(0.25)

    async def run(self):
        try:
            port = await self._start_server()
            await self._start_browser(port)
            await self._wait_until_ready()
            self.camera._webrtc_retry_delay = 15.0
            next_extension = (
                asyncio.get_running_loop().time() + self.camera._extension_interval
            )
            while not self.camera._terminate_signal.is_set():
                if self.camera._webrtc_restart.is_set():
                    self.logger.warning("A Chromium WebRTC session restart was requested")
                    return
                if self.failure is not None:
                    raise self.failure
                if self.browser.returncode is not None:
                    raise RuntimeError(
                        f"Chromium exited unexpectedly (status {self.browser.returncode})"
                    )
                if time.monotonic() - self.last_status > 20:
                    raise TimeoutError("Chromium stopped reporting WebRTC health")

                now = asyncio.get_running_loop().time()
                if now >= next_extension:
                    extension = await self.camera._send_command_async(
                        "CameraLiveStream.ExtendWebRtcStream",
                        {"mediaSessionId": self.media_session_id},
                    )
                    results = extension["results"]
                    self.media_session_id = results.get(
                        "mediaSessionId", self.media_session_id
                    )
                    self.camera._media_session_id = self.media_session_id
                    self.camera._record_expiration(
                        results["expiresAt"], "Extended Chromium WebRTC session"
                    )
                    next_extension = now + self.camera._extension_interval
                await asyncio.sleep(1)
        finally:
            await self.close()

    async def close(self):
        if self.browser is not None and self.browser.returncode is None:
            self.browser.terminate()
            try:
                await asyncio.wait_for(self.browser.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.browser.kill()
                await self.browser.wait()
        if self.http is not None:
            if self.whip_resource_url:
                try:
                    async with self.http.delete(
                        self.whip_resource_url,
                        auth=self.camera._webrtc_publish_auth(self._aiohttp),
                    ):
                        pass
                except Exception as error:
                    self.logger.debug("Could not delete Chromium WHIP session: %r", error)
            await self.http.close()
        if self.runner is not None:
            await self.runner.cleanup()
        elif self.socket is not None:
            self.socket.close()
        if self.media_session_id:
            try:
                await self.camera._send_command_async(
                    "CameraLiveStream.StopWebRtcStream",
                    {"mediaSessionId": self.media_session_id},
                )
            except Exception as error:
                self.logger.debug("Could not stop Google Chromium session: %r", error)
        self.camera._media_session_id = None
        if self.profile is not None:
            self.profile.cleanup()
