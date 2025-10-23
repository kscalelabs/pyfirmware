"""WebRTC server using GStreamer and websockets for streaming video/audio."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
from typing import Optional

import gi  # type: ignore[import-not-found]
import websockets  # type: ignore[import-not-found]
from gi.repository import GLib, Gst, GstSdp, GstWebRTC  # type: ignore[import-not-found]

gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
gi.require_version("GstSdp", "1.0")
Gst.init(None)

TURN_URL = f"turn://{os.getenv('TURN_USERNAME')}:{os.getenv('TURN_PASSWORD')}@{os.getenv('TURN_SERVER')}"

WEBRTC_DESC = """
webrtcbin name=sendrecv
    bundle-policy=max-bundle
    stun-server=stun://stun.l.google.com:19302
"""

VIDEO_SOURCES = [
    "/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36",
    "/base/axi/pcie@1000120000/rp1/i2c@80000/ov5647@36",
]

AUDIO_SOURCE = "hw:0,0"

async def glib_main_loop_iteration() -> None:
    while True:
        while GLib.main_context_default().iteration(False):
            pass
        await asyncio.sleep(0.01)

def add_elements_to_pipeline(pipeline: Gst.Pipeline, elements: list[Gst.Element]) -> None:
    for element in elements:
        pipeline.add(element)
        element.sync_state_with_parent()

    for i in range(len(elements) - 1):
        elements[i].link(elements[i + 1])

class WebRTCServer:
    def __init__(self, loop: asyncio.AbstractEventLoop, flip_video: bool = False) -> None:
        self.pipe: Optional[Gst.Pipeline] = None
        self.webrtc: Optional[GstWebRTC.WebRTCBin] = None
        self.ws: Optional[websockets.WebSocketServerProtocol] = None
        self.loop = loop
        self.added_data_channel = False
        self.added_streams = 0
        self.flip_video = flip_video
        self.udp_target = ("127.0.0.1", 10000) # To Forward Data Channel Commands
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def cleanup(self) -> None:
        if self.pipe:
            self.close_pipeline()
        if self.udp_sock:
            self.udp_sock.close()

    def connect_microphone(self, webrtc: GstWebRTC.WebRTCBin) -> None:
        if self.pipe is None:
            print("Error: Pipeline not initialized")
            return

        audio_src = Gst.ElementFactory.make("alsasrc", "audio_src")
        audio_conv = Gst.ElementFactory.make("audioconvert", "audio_conv")
        audio_resample = Gst.ElementFactory.make("audioresample", "audio_resample")
        opus_enc = Gst.ElementFactory.make("opusenc", "opus_enc")
        rtp_pay = Gst.ElementFactory.make("rtpopuspay", "rtp_pay")
        rtp_pay.set_property("pt", 98)

        elements_to_add = [audio_src, audio_conv, audio_resample, opus_enc, rtp_pay]

        add_elements_to_pipeline(self.pipe, elements_to_add)

        sink_pad = webrtc.get_request_pad("sink_1")
        src_pad = rtp_pay.get_static_pad("src")

        if not sink_pad or not src_pad:
            print("Failed to get pads for linking audio")
            return

        ret = src_pad.link(sink_pad)
        if ret != Gst.PadLinkReturn.OK:
            print("Failed to link audio to webrtcbin:", ret)
        else:
            print("Audio linked to webrtcbin")

    def start_pipeline(self, active_cameras: list[int] = [1], audio: bool = True) -> None:
        print("Starting pipeline")
        self.pipe = Gst.Pipeline.new("pipeline")
        webrtc = Gst.parse_launch(WEBRTC_DESC)
        webrtc.set_property("turn-server", TURN_URL)
        webrtc.set_property("ice-transport-policy", "all")

        self.pipe.add(webrtc)

        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus_message)

        self.webrtc = self.pipe.get_by_name("sendrecv")
        self.webrtc.set_property("latency", 0)
        self.webrtc.connect("on-ice-candidate", self.send_ice_candidate_message)
        self.webrtc.connect("on-data-channel", self.on_data_channel)
        self.webrtc.connect("pad-added", self.on_incoming_stream)

        video_sources = []
        for i in range(len(active_cameras)):
            video_sources.append(VIDEO_SOURCES[active_cameras[i]])

        for i, cam_name in enumerate(video_sources):
            src = Gst.ElementFactory.make("libcamerasrc", f"libcamerasrc{i}")
            src.set_property("camera-name", cam_name)

            caps = Gst.Caps.from_string("video/x-raw,format=YUY2,width=640,height=480,framerate=30/1")
            capsfilter = Gst.ElementFactory.make("capsfilter", f"caps{i}")
            capsfilter.set_property("caps", caps)

            conv = Gst.ElementFactory.make("videoconvert", f"conv{i}")

            sink_queue = Gst.ElementFactory.make("queue", f"sink_queue{i}")
            sink_queue.set_property("leaky", 2)
            sink_queue.set_property("max-size-buffers", 2)

            elements_to_add = [src, capsfilter, conv, sink_queue]

            if not self.flip_video:
                flip = Gst.ElementFactory.make("videoflip", f"flip{i}")
                flip.set_property("method", 2)  # 2 = vertical flip
                elements_to_add.append(flip)

            vp8enc = Gst.ElementFactory.make("vp8enc", f"vp8enc{i}")
            vp8enc.set_property("deadline", 1)
            vp8enc.set_property("keyframe-max-dist", 30)

            pay = Gst.ElementFactory.make("rtpvp8pay", f"pay{i}")
            pay.set_property("pt", 96 + i)

            elements_to_add.extend([vp8enc, pay])

            add_elements_to_pipeline(self.pipe, elements_to_add)

            src_pad = src.get_static_pad("src")
            sink_pad = webrtc.get_request_pad(f"sink_{i * 2}")
            if not sink_pad:
                print(f"Failed to get sink pad for stream {i}")
            else:
                src_pad = pay.get_static_pad("src")
                ret = src_pad.link(sink_pad)
                print("Pad link result", ret)

        if audio:
            self.connect_microphone(webrtc)

        self.webrtc.connect("on-negotiation-needed", self.on_negotiation_needed)
        self.pipe.set_state(Gst.State.PLAYING)

        print("Pipeline started")

    def on_bus_message(self, bus: Gst.Bus, message: Gst.Message) -> int:
        if message.type == Gst.MessageType.LATENCY:
            if self.pipe is not None:
                self.pipe.recalculate_latency()

        return GLib.SOURCE_CONTINUE

    def close_pipeline(self) -> None:
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            self.pipe, self.webrtc, self.added_data_channel = None, None, False

    def on_message_string(self, channel: GstWebRTC.WebRTCDataChannel, message: str) -> None:
        """Handle incoming messages from WebRTC data channel and forward to UDP listener."""
        try:
            msg = {"commands": json.loads(message)}
            self.udp_sock.sendto(json.dumps(msg).encode("utf-8"), self.udp_target)
        except Exception as e:
            print(f"Error forwarding command: {e}")

    def on_data_channel(self, webrtc: GstWebRTC.WebRTCBin, channel: GstWebRTC.WebRTCDataChannel) -> None:
        print("New data channel:", channel.props.label)
        channel.connect("on-message-string", self.on_message_string)

    def on_incoming_stream(self, _: GstWebRTC.WebRTCBin, pad: Gst.Pad) -> None:
        if pad.direction != Gst.PadDirection.SRC:
            return

        caps = pad.get_current_caps()
        if not caps:
            print("No caps available for incoming stream")
            return

        structure = caps.get_structure(0)
        media_type = structure.get_string("media")
        encoding_name = structure.get_string("encoding-name")

        print(f"Incoming stream - Media: {media_type}, Encoding: {encoding_name}")

        if media_type == "video" and encoding_name == "VP8":
            stream_id = self.added_streams

            vp8depay = Gst.ElementFactory.make("rtpvp8depay", f"vp8depay_{stream_id}")
            vp8dec = Gst.ElementFactory.make("vp8dec", f"vp8dec_{stream_id}")
            queue2 = Gst.ElementFactory.make("queue", f"queue2_{stream_id}")
            videoconvert = Gst.ElementFactory.make("videoconvert", f"videoconvert_{stream_id}")

            videoscale = Gst.ElementFactory.make("videoscale", f"videoscale_{stream_id}")
            videoscale.set_property("method", 1)  # Bilinear scaling
            videoscale.set_property("add-borders", True)  # Add black bars to maintain aspect ratio

            scale_caps = Gst.Caps.from_string("video/x-raw,width=1024,height=600")
            scale_capsfilter = Gst.ElementFactory.make("capsfilter", f"scale_caps_{stream_id}")
            scale_capsfilter.set_property("caps", scale_caps)

            videosink = Gst.ElementFactory.make("kmssink", f"kmssink_{stream_id}")
            if videosink:
                videosink.set_property("connector-id", -1)
                videosink.set_property("can-scale", True)
            else:
                print(f"Warning: Failed to create kmssink for stream {stream_id}")
                videosink = Gst.ElementFactory.make("fakesink", f"fakesink_{stream_id}")

            vp8depay.set_property("request-keyframe", True)
            vp8depay.set_property("wait-for-keyframe", False)

            elements = [vp8depay, vp8dec, queue2, videoconvert, videoscale, scale_capsfilter, videosink]
            add_elements_to_pipeline(self.pipe, elements)

            sink_pad = vp8depay.get_static_pad("sink")
            pad.link(sink_pad)

        elif media_type == "audio" and encoding_name == "OPUS":
            stream_id = self.added_streams

            opusdepay = Gst.ElementFactory.make("rtpopusdepay", f"opusdepay_{stream_id}")
            opusdec = Gst.ElementFactory.make("opusdec", f"opusdec_{stream_id}")
            audioconvert = Gst.ElementFactory.make("audioconvert", f"audioconvert_{stream_id}")
            audioresample = Gst.ElementFactory.make("audioresample", f"audioresample_{stream_id}")
            autoaudiosink = Gst.ElementFactory.make("autoaudiosink", f"autoaudiosink_{stream_id}")
            autoaudiosink.set_property("sync", True)

            add_elements_to_pipeline(self.pipe, [opusdepay, opusdec, audioconvert, audioresample, autoaudiosink])

            sink_pad = opusdepay.get_static_pad("sink")
            pad.link(sink_pad)

        else:
            print(f"Unsupported stream type: {media_type}/{encoding_name}")

        self.added_streams += 1

    def on_negotiation_needed(self, element: GstWebRTC.WebRTCBin) -> None:
        """Triggered by webrtcbin when media streams are connected to sink pad."""
        print("Media Stream Connected, Negotiating...")
        if self.added_data_channel or self.webrtc is None:
            return

        self.added_data_channel = True
        self.data_channel = self.webrtc.emit("create-data-channel", "chat", None)

        if self.data_channel:
            self.data_channel.connect("on-message-string", self.on_message_string)

        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)
        if self.webrtc is not None:
            self.webrtc.emit("create-offer", None, promise)

    def on_offer_created(self, promise: Gst.Promise, _: GstWebRTC.WebRTCBin, __: None) -> None:
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value("offer")
        if self.webrtc is not None:
            self.webrtc.emit("set-local-description", offer, Gst.Promise.new())
        print("Sending SDP Offer")
        message = json.dumps({"sdp": {"type": "offer", "sdp": offer.sdp.as_text()}})
        if self.ws is not None:
            asyncio.run_coroutine_threadsafe(self.ws.send(message), self.loop)

    def send_ice_candidate_message(self, _: GstWebRTC.WebRTCBin, mlineindex: int, candidate: str) -> None:
        message = json.dumps({"ice": {"candidate": candidate, "sdpMLineIndex": mlineindex}})
        if self.ws is not None:
            asyncio.run_coroutine_threadsafe(self.ws.send(message), self.loop)

    def handle_client_message(self, message: str) -> None:
        msg = json.loads(message)
        msg_type = msg.get("type", None)

        if "sdp" in msg and msg["sdp"]["type"] == "answer":
            print("Received SDP Answer")
            sdp = msg["sdp"]["sdp"]
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(sdp.encode(), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            if self.webrtc is not None:
                self.webrtc.emit("set-remote-description", answer, Gst.Promise.new())

        elif "ice" in msg:
            ice = msg["ice"]
            if self.webrtc is not None:
                self.webrtc.emit("add-ice-candidate", ice["sdpMLineIndex"], ice["candidate"])

        elif msg_type == "HELLO":
            print("Restarting Pipeline")
            if self.pipe:
                self.close_pipeline()
            self.start_pipeline(msg.get("cameras", [0]), msg.get("audio", True))

    async def websocket_handler(self, ws: websockets.WebSocketServerProtocol) -> None:
        print("Client connected")
        self.ws = ws
        async for msg in ws:
            self.handle_client_message(msg)

        print("Client disconnected, Stopping Pipeline")
        self.close_pipeline()

async def main() -> None:
    parser = argparse.ArgumentParser(description="WebRTC Video Streaming Server")
    parser.add_argument("--flip", action="store_true", help="Vertically flip the video stream")
    args = parser.parse_args()

    loop = asyncio.get_running_loop()
    server = WebRTCServer(loop, flip_video=args.flip)

    async def handler(websocket: websockets.WebSocketServerProtocol) -> None:
        await server.websocket_handler(websocket)

    try:
        asyncio.create_task(glib_main_loop_iteration())
        async with websockets.serve(handler, "0.0.0.0", 8765):
            print("WebSocket server running on ws://0.0.0.0:8765")
            await asyncio.Future()
    finally:
        server.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
