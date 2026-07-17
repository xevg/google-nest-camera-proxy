import asyncio
import datetime
import json
import logging
import threading
import time
from configparser import ConfigParser
from typing import Optional, Set

import nest
import nest.nest
from dateutil import parser
from dateutil import tz


CAMERA_LIVE_STREAM_TRAIT = "CameraLiveStream"
RTSP_PROTOCOL = "RTSP"
WEBRTC_PROTOCOL = "WEB_RTC"


class UnsupportedCameraProtocol(RuntimeError):
    """Raised when SDM does not advertise a protocol this proxy can use."""


def _get_legal_camera_name(name: str) -> str:
    legal_characters = (
        "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_.~-"
    )
    return "".join(character for character in name if character in legal_characters)


class Camera:
    """A Nest camera streamed into MediaMTX through RTSP or WebRTC/WHIP."""

    # Sandbox allows 10 ExecuteDeviceCommand calls per minute per user. All
    # Camera instances share this lock so startup, renewal, retry, and cleanup
    # commands cannot create a cross-camera burst.
    _command_lock = threading.Lock()
    _last_command_time = 0.0

    def __init__(
        self,
        configuration: ConfigParser,
        device: nest.nest.Device,
        device_name: str,
        device_id: str,
    ) -> None:
        self._configuration = configuration
        self._camera = device
        self._name = device_name
        self._device_id = device_id
        self._legal_camera_name = _get_legal_camera_name(self._name)
        self._logger = logging.getLogger(self._legal_camera_name)

        self._stream_url: Optional[str] = None
        self._stream_reset = True
        self._terminate_signal = threading.Event()
        self._webrtc_restart = threading.Event()
        self._webrtc_thread: Optional[threading.Thread] = None
        self._timer: Optional[threading.Timer] = None

        self._stream_extension_token: Optional[str] = None
        self._stream_token: Optional[str] = None
        self._media_session_id: Optional[str] = None
        self._expires_at: Optional[str] = None
        self._expiration_time: Optional[datetime.datetime] = None

        # SDM sessions expire after five minutes. Renew with a safety margin.
        self._extension_interval = 4.5 * 60
        self._command_interval = self._configuration.getfloat(
            "RTSP_SERVER", "sdm_command_interval", fallback=6.5
        )
        self._webrtc_retry_delay = 15.0
        self._webrtc_retry_max = self._configuration.getfloat(
            "RTSP_SERVER", "webrtc_retry_max", fallback=300.0
        )
        self._webrtc_video_start_timeout = self._configuration.getfloat(
            "RTSP_SERVER", "webrtc_video_start_timeout", fallback=60.0
        )
        self._supported_protocols = self._read_supported_protocols()
        self._stream_protocol = self._choose_protocol(self._supported_protocols)

        self._logger.warning(
            "%s supports %s; selected %s",
            self.legal_camera_name,
            sorted(self._supported_protocols),
            self._stream_protocol,
        )

        if self._stream_protocol == RTSP_PROTOCOL:
            self._get_rtsp_token()
            self._schedule_rtsp_renewal()
        else:
            # MediaMTX must be running before a WHIP publisher can connect.
            # GoogleNestCameraProxy.run() starts this camera after MediaMTX.
            self._stream_url = "publisher"

    def __del__(self):
        try:
            self.terminate()
        except Exception:
            # Destructors must never raise during interpreter shutdown.
            pass

    def _read_supported_protocols(self) -> Set[str]:
        trait = self._camera.traits.get(CAMERA_LIVE_STREAM_TRAIT)
        if not isinstance(trait, dict):
            raise UnsupportedCameraProtocol(
                f"{self.legal_camera_name} has no {CAMERA_LIVE_STREAM_TRAIT} trait"
            )

        protocols = trait.get("supportedProtocols", [])
        if not isinstance(protocols, list):
            raise UnsupportedCameraProtocol(
                f"{self.legal_camera_name} returned invalid supportedProtocols: "
                f"{protocols!r}"
            )
        return {str(protocol).upper() for protocol in protocols}

    @staticmethod
    def _choose_protocol(protocols: Set[str]) -> str:
        # Prefer RTSP when Google advertises both, preserving the original,
        # pass-through behavior and avoiding WebRTC transcoding.
        if RTSP_PROTOCOL in protocols:
            return RTSP_PROTOCOL
        if WEBRTC_PROTOCOL in protocols:
            return WEBRTC_PROTOCOL
        raise UnsupportedCameraProtocol(
            f"Camera supports neither RTSP nor WEB_RTC (reported {sorted(protocols)})"
        )

    def start(self) -> None:
        """Start the active WebRTC bridge. RTSP cameras start in __init__."""
        if self._stream_protocol != WEBRTC_PROTOCOL:
            return
        if self._webrtc_thread is not None and self._webrtc_thread.is_alive():
            return

        self._webrtc_thread = threading.Thread(
            target=self._run_webrtc_thread,
            name=f"{self.legal_camera_name} WebRTC Bridge",
        )
        self._webrtc_thread.start()

    def reset(self) -> None:
        self._logger.warning("%s resetting", self.legal_camera_name)
        if self._stream_protocol == RTSP_PROTOCOL:
            self._get_rtsp_token()
            self._stream_reset = True
        else:
            # The supervisor cleans up both peer connections and negotiates a
            # fresh Google session and a fresh MediaMTX WHIP session.
            self._webrtc_restart.set()

    @property
    def name(self) -> str:
        return self._name.replace(" ", "_")

    @property
    def stream_url(self) -> str:
        return self._stream_url or "publisher"

    @property
    def legal_camera_name(self) -> str:
        return self._legal_camera_name

    @property
    def supported_protocols(self) -> Set[str]:
        return set(self._supported_protocols)

    @property
    def stream_protocol(self) -> str:
        return self._stream_protocol

    @property
    def stream_reset(self) -> bool:
        return self._stream_reset

    @stream_reset.setter
    def stream_reset(self, stream_reset: bool):
        self._logger.debug("Resetting configuration")
        self._stream_reset = stream_reset

    def _get_rtsp_token(self) -> None:
        """Get a new RTSP stream URL and extension token."""
        while not self._terminate_signal.is_set():
            try:
                response = self._send_command(
                    "CameraLiveStream.GenerateRtspStream", json.loads("{}")
                )
                results = response["results"]
                self._stream_url = results["streamUrls"]["rtspUrl"]
                self._stream_token = results["streamToken"]
                self._stream_extension_token = results["streamExtensionToken"]
                self._record_expiration(results["expiresAt"], "Got RTSP token")
                return
            except nest.APIError as error:
                self._logger.error(
                    "Received a Nest APIError authenticating RTSP camera: %r; "
                    "sleeping and trying again",
                    error,
                )
            except Exception as error:
                self._logger.error(
                    "Unexpected error getting RTSP token: %r (%s)",
                    error,
                    type(error).__name__,
                )
            self._terminate_signal.wait(30)

    def _schedule_rtsp_renewal(self) -> None:
        if self._terminate_signal.is_set():
            return
        self._timer = threading.Timer(self._extension_interval, self._renew_rtsp_token)
        self._timer.name = f"{self.legal_camera_name} Extension Timer"
        self._timer.start()

    def _renew_rtsp_token(self) -> None:
        if self._terminate_signal.is_set():
            return

        try:
            response = self._send_command(
                "CameraLiveStream.ExtendRtspStream",
                {"streamExtensionToken": self._stream_extension_token},
            )
            results = response["results"]
            self._stream_extension_token = results["streamExtensionToken"]
            self._stream_token = results.get("streamToken", self._stream_token)
            self._record_expiration(results["expiresAt"], "Renewed RTSP token")
        except nest.APIError as error:
            self._logger.error(
                "Received a Nest APIError extending RTSP stream: %r; "
                "getting a new token",
                error,
            )
            self._get_rtsp_token()
        except Exception as error:
            self._logger.error(
                "Unexpected error extending RTSP token: %r (%s); "
                "getting a new token",
                error,
                type(error).__name__,
            )
            self._get_rtsp_token()
        finally:
            self._schedule_rtsp_renewal()

    def _record_expiration(self, expires_at: str, action: str) -> None:
        self._expires_at = expires_at
        self._expiration_time = parser.isoparse(expires_at).astimezone(tz.tzlocal())
        remaining = self._expiration_time - datetime.datetime.now(tz.tzlocal())
        self._logger.info(
            "%s for %s; expiration: %s; time remaining: %s",
            action,
            self.legal_camera_name,
            str(self._expiration_time).split(".")[0],
            str(remaining).split(".")[0],
        )

    def _run_webrtc_thread(self) -> None:
        try:
            asyncio.run(self._webrtc_supervisor())
        except Exception:
            self._logger.exception("WebRTC supervisor stopped unexpectedly")

    async def _webrtc_supervisor(self) -> None:
        while not self._terminate_signal.is_set():
            self._webrtc_restart.clear()
            try:
                await self._run_webrtc_session()
            except Exception as error:
                if self._terminate_signal.is_set():
                    return
                self._logger.error(
                    "WebRTC bridge failed: %r (%s)",
                    error,
                    type(error).__name__,
                    exc_info=self._logger.isEnabledFor(logging.DEBUG),
                )

            if self._terminate_signal.is_set():
                return
            if self._webrtc_restart.is_set():
                # Explicit resets should reconnect immediately; the delay is
                # only for failures, where it protects the SDM rate limit.
                continue
            retry_delay = self._webrtc_retry_delay
            self._webrtc_retry_delay = min(
                self._webrtc_retry_delay * 2, self._webrtc_retry_max
            )
            self._logger.warning(
                "Retrying WebRTC bridge in %.0f seconds", retry_delay
            )
            for _ in range(max(1, int(retry_delay))):
                if self._terminate_signal.is_set():
                    return
                await asyncio.sleep(1)

    async def _run_webrtc_session(self) -> None:
        from .browser_bridge import BrowserWebRTCSession

        await BrowserWebRTCSession(self).run()

    @staticmethod
    def _normalize_google_answer_sdp(sdp: str):
        """Add the omitted ICE component ID used by some migrated cameras.

        RFC 5245 candidates place a numeric component ID between the foundation
        and transport. Some Google SDM answers instead return lines beginning
        ``a=candidate:<foundation> udp ...``. Chromium expects the numeric
        field when applying Google's answer.
        """
        normalized_lines = []
        normalized_count = 0
        for line in sdp.splitlines(keepends=True):
            body = line.rstrip("\r\n")
            line_ending = line[len(body) :]
            prefix = "a=candidate:"
            if body.startswith(prefix):
                candidate_parts = body[len(prefix) :].split()
                if (
                    len(candidate_parts) >= 2
                    and candidate_parts[1].lower() in ("udp", "tcp")
                ):
                    candidate_parts.insert(1, "1")
                    body = prefix + " ".join(candidate_parts)
                    normalized_count += 1
            normalized_lines.append(body + line_ending)
        return "".join(normalized_lines), normalized_count

    @staticmethod
    def _summarize_sdp_media(sdp: str) -> str:
        """Return media, direction, and codecs without credentials/candidates."""
        summaries = []
        current = None
        for raw_line in sdp.splitlines():
            line = raw_line.strip()
            if line.startswith("m="):
                if current is not None:
                    summaries.append(current)
                parts = line[2:].split()
                current = {
                    "kind": parts[0] if parts else "unknown",
                    "port": parts[1] if len(parts) > 1 else "?",
                    "direction": "unspecified",
                    "codecs": [],
                }
            elif current is not None and line in (
                "a=sendrecv",
                "a=sendonly",
                "a=recvonly",
                "a=inactive",
            ):
                current["direction"] = line[2:]
            elif current is not None and line.startswith("a=rtpmap:"):
                codec = line.split(None, 1)
                if len(codec) == 2:
                    current["codecs"].append(codec[1].split("/", 1)[0])
        if current is not None:
            summaries.append(current)
        return repr(summaries)

    async def _send_command_async(self, command: str, parameters: dict) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self._send_command(command, parameters)
        )

    def _send_command(self, command: str, parameters: dict) -> dict:
        """Execute an SDM command without exceeding the per-user Sandbox QPM."""
        with Camera._command_lock:
            elapsed = time.monotonic() - Camera._last_command_time
            wait_time = self._command_interval - elapsed
            if wait_time > 0:
                self._logger.info(
                    "Waiting %.1f seconds for the shared SDM command quota",
                    wait_time,
                )
                if self._terminate_signal.wait(wait_time):
                    raise RuntimeError("Camera terminated while waiting for SDM quota")
            try:
                return self._camera.send_cmd(command, parameters)
            finally:
                Camera._last_command_time = time.monotonic()

    def _webrtc_publish_url(self) -> str:
        template = self._configuration.get(
            "RTSP_SERVER",
            "webrtc_publish_url",
            fallback="http://127.0.0.1:8889/{camera}/whip",
        )
        return template.format(
            camera=self.legal_camera_name, camera_name=self.legal_camera_name
        )

    def _webrtc_publish_auth(self, aiohttp_module):
        username = self._configuration.get(
            "RTSP_SERVER", "webrtc_publish_user", fallback=""
        )
        if not username:
            return None
        password = self._configuration.get(
            "RTSP_SERVER", "webrtc_publish_password", fallback=""
        )
        return aiohttp_module.BasicAuth(username, password)

    def request_terminate(self) -> None:
        """Signal shutdown without waiting for this camera's worker."""
        if self._terminate_signal.is_set():
            return
        self._logger.warning("%s terminating", self.legal_camera_name)
        self._terminate_signal.set()
        self._webrtc_restart.set()
        if self._timer is not None:
            self._timer.cancel()

    def terminate(self) -> None:
        self.request_terminate()
        if (
            self._webrtc_thread is not None
            and self._webrtc_thread.is_alive()
            and threading.current_thread() is not self._webrtc_thread
        ):
            self._webrtc_thread.join(timeout=10)

    def __lt__(self, obj):
        return self.legal_camera_name < obj.legal_camera_name

    def __gt__(self, obj):
        return self.legal_camera_name > obj.legal_camera_name

    def __le__(self, obj):
        return self.legal_camera_name <= obj.legal_camera_name

    def __ge__(self, obj):
        return self.legal_camera_name >= obj.legal_camera_name

    def __eq__(self, obj):
        return self.legal_camera_name == obj.legal_camera_name
