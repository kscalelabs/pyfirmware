"""WebRTC server using GStreamer and websockets for streaming video/audio."""

import argparse
import asyncio
import json
import os
import time
from typing import Optional

import gi  # type: ignore[import-not-found]
import websockets  # type: ignore[import-not-found]
from gi.repository import GLib, Gst, GstSdp, GstWebRTC  # type: ignore[import-not-found]

gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
gi.require_version("GstSdp", "1.0")


Gst.init(None)
TURN_URL = f"turn://{os.getenv('TURN_USERNAME')}:{os.getenv('TURN_PASSWORD')}@{os.getenv('TURN_SERVER')}"
PIPELINE_DESC = """
webrtcbin name=sendrecv
    bundle-policy=max-bundle
    stun-server=stun://stun.l.google.com:19302
"""
# ice-transport-policy=relay
VIDEO_SOURCES = [
    "/base/axi/pcie@1000120000/rp1/i2c@80000/ov5647@36",
    "/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36",
]

AUDIO_SOURCE = "hw:0,0"


async def glib_main_loop_iteration() -> None:
    while True:
        # Process all pending GLib events without blocking
        while GLib.main_context_default().iteration(False):
            pass
        # Yield control back to asyncio, adjust delay as needed
        await asyncio.sleep(0.01)


class WebRTCServer:
    def __init__(self, loop: asyncio.AbstractEventLoop, flip_video: bool = False) -> None:
        self.pipe: Optional[Gst.Pipeline] = None
        self.webrtc: Optional[GstWebRTC.WebRTCBin] = None
        self.ws: Optional[websockets.WebSocketServerProtocol] = None  # active client connection
        self.loop = loop
        self.added_data_channel = False
        self.added_streams = 0
        self.flip_video = flip_video
        self.first_frame_timestamp: Optional[float] = None

    def connect_audio(self, webrtc: GstWebRTC.WebRTCBin) -> None:
        if self.pipe is None:
            print("Error: Pipeline not initialized")
            return
        audio_src = Gst.ElementFactory.make("alsasrc", "audio_src")
        audio_conv = Gst.ElementFactory.make("audioconvert", "audio_conv")
        audio_resample = Gst.ElementFactory.make("audioresample", "audio_resample")
        opus_enc = Gst.ElementFactory.make("opusenc", "opus_enc")
        rtp_pay = Gst.ElementFactory.make("rtpopuspay", "rtp_pay")
        rtp_pay.set_property("pt", 98)

        for e in [audio_src, audio_conv, audio_resample, opus_enc, rtp_pay]:
            self.pipe.add(e)

        audio_src.link(audio_conv)
        audio_conv.link(audio_resample)
        audio_resample.link(opus_enc)
        opus_enc.link(rtp_pay)

        # --- Request audio pad from webrtcbin ---
        # Use caps for RTP/OPUS
        sink_pad = webrtc.get_request_pad("sink_1")  # or "sink_%u" may work
        src_pad = rtp_pay.get_static_pad("src")

        if not sink_pad or not src_pad:
            print("Failed to get pads for linking audio")
            return

        ret = src_pad.link(sink_pad)
        if ret != Gst.PadLinkReturn.OK:
            print("Failed to link audio to webrtcbin:", ret)
        else:
            print("Audio linked to webrtcbin")

    def start_pipeline(self, active_cameras: list[int] = [1], audio: bool = True, undistort: bool = False) -> None:
        print("Starting pipeline")
        self.pipe = Gst.Pipeline.new("pipeline")
        webrtc = Gst.parse_launch(PIPELINE_DESC)
        webrtc.set_property("turn-server", TURN_URL)
        webrtc.set_property("ice-transport-policy", "all")
        self.pipe.add(webrtc)
        print(self.pipe)

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
            # Source + capsfilter: force YUY2 output
            src = Gst.ElementFactory.make("libcamerasrc", f"libcamerasrc{i}")
            src.set_property("camera-name", cam_name)

            caps = Gst.Caps.from_string("video/x-raw,format=YUY2,width=640,height=480,framerate=30/1")
            capsfilter = Gst.ElementFactory.make("capsfilter", f"caps{i}")
            capsfilter.set_property("caps", caps)

            # Convert to BGR for OpenCV
            conv = Gst.ElementFactory.make("videoconvert", f"conv{i}")

            # Add videoflip element only if flip is enabled
            if self.flip_video:
                flip = Gst.ElementFactory.make("videoflip", f"flip{i}")
                flip.set_property("method", 2)  # 2 = vertical flip

            sink_queue = Gst.ElementFactory.make("queue", f"sink_queue{i}")
            sink_queue.set_property("leaky", 2)
            sink_queue.set_property("max-size-buffers", 2)

            elements_to_add = [src, capsfilter, conv, sink_queue]
            if self.flip_video:
                elements_to_add.append(flip)

            for e in elements_to_add:
                self.pipe.add(e)

            # Link source -> conv -> queue (with optional flip)
            src.link(capsfilter)
            capsfilter.link(conv)

            if self.flip_video:
                conv.link(flip)
                flip.link(sink_queue)
            else:
                conv.link(sink_queue)

            upstream_element = sink_queue

            vp8enc = Gst.ElementFactory.make("vp8enc", f"vp8enc{i}")
            vp8enc.set_property("deadline", 1)
            vp8enc.set_property("keyframe-max-dist", 30)
            pay = Gst.ElementFactory.make("rtpvp8pay", f"pay{i}")
            pay.set_property("pt", 96 + i)

            # Add elements to pipeline
            for e in [vp8enc, pay]:
                self.pipe.add(e)

            upstream_element.link(vp8enc)
            vp8enc.link(pay)
            print(f"Camera {i} encoding: AppSrc (BGR) -> VideoConvert -> Scale(1920x1080) -> I420 -> VP8 -> RTP")

            src_pad = src.get_static_pad("src")
            sink_pad = webrtc.get_request_pad(f"sink_{i * 2}")
            if not sink_pad:
                print(f"Failed to get sink pad for stream {i}")
            else:
                src_pad = pay.get_static_pad("src")
                ret = src_pad.link(sink_pad)
                print("Pad link result", ret)

        # if audio:
        #     self.connect_audio(webrtc)
        self.webrtc.connect("on-negotiation-needed", self.on_negotiation_needed)
        self.pipe.set_state(Gst.State.PLAYING)
        Gst.debug_bin_to_dot_file(self.pipe, Gst.DebugGraphDetails.ALL, "pipeline_graph")

        print("Pipeline started")

    def on_bus_message(self, bus: Gst.Bus, message: Gst.Message) -> int:
        """Handle messages from the GStreamer bus, specifically for latency."""
        t = message.type
        if t == Gst.MessageType.LATENCY:
            print("Received a LATENCY message. Recalculating latency.")
            if self.pipe is not None:
                self.pipe.recalculate_latency()
        elif t == Gst.MessageType.STATE_CHANGED:
            # Capture timestamp when pipeline starts playing (first frame flows)
            if message.src == self.pipe and self.first_frame_timestamp is None:
                old_state, new_state, pending = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    self.first_frame_timestamp = time.time()
                    print(f"First frame timestamp: {self.first_frame_timestamp} (wall clock time)")
                    print(f"First frame time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.first_frame_timestamp))}")

        return GLib.SOURCE_CONTINUE

    def close_pipeline(self) -> None:
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            self.pipe = None
            self.webrtc = None
            self.added_data_channel = False
            self.first_frame_timestamp = None  # Reset for next pipeline

    def on_message_string(self, channel: GstWebRTC.WebRTCDataChannel, message: str) -> None:
        print("Received:", message)

    def on_data_channel(self, webrtc: GstWebRTC.WebRTCBin, channel: GstWebRTC.WebRTCDataChannel) -> None:
        print("New data channel:", channel.props.label)
        channel.connect("on-message-string", self.on_message_string)

    def on_incoming_stream(self, _: GstWebRTC.WebRTCBin, pad: Gst.Pad) -> None:
        if pad.direction != Gst.PadDirection.SRC:
            return

        # Get the caps to determine if this is video or audio
        caps = pad.get_current_caps()
        if not caps:
            print("No caps available for incoming stream")
            return

        structure = caps.get_structure(0)
        media_type = structure.get_string("media")
        encoding_name = structure.get_string("encoding-name")

        print(f"Incoming stream - Media: {media_type}, Encoding: {encoding_name}")

        if media_type == "video" and encoding_name == "VP8":
            # Create video pipeline with proper synchronization
            stream_id = self.added_streams

            # Create elements
            vp8depay = Gst.ElementFactory.make("rtpvp8depay", f"vp8depay_{stream_id}")
            vp8dec = Gst.ElementFactory.make("vp8dec", f"vp8dec_{stream_id}")
            queue2 = Gst.ElementFactory.make("queue", f"queue2_{stream_id}")
            videoconvert = Gst.ElementFactory.make("videoconvert", f"videoconvert_{stream_id}")
            videoscale = Gst.ElementFactory.make("videoscale", f"videoscale_{stream_id}")

            # Configure scaling to fit within 1920x1080 while preserving aspect ratio
            videoscale.set_property("method", 1)  # Bilinear scaling
            scale_caps = Gst.Caps.from_string("video/x-raw,width=1920,height=1080")
            scale_capsfilter = Gst.ElementFactory.make("capsfilter", f"scale_caps_{stream_id}")
            scale_capsfilter.set_property("caps", scale_caps)

            # Use glimagesink directly with fullscreen/borderless properties
            autovideosink = Gst.ElementFactory.make("glimagesink", f"glimagesink_{stream_id}")
            autovideosink.set_property("force-aspect-ratio", True)

            # Configure depayloader properties
            vp8depay.set_property("request-keyframe", True)
            vp8depay.set_property("wait-for-keyframe", False)  # Changed to False

            # vp8dec.set_property("deblock", False)

            # Configure queue properties for better flow control

            # Add elements to pipeline
            elements = [vp8depay, vp8dec, queue2, videoconvert, videoscale, scale_capsfilter, autovideosink]
            for element in elements:
                if self.pipe is not None:
                    self.pipe.add(element)
                element.sync_state_with_parent()

            # Link elements in order: depay -> dec -> queue -> convert -> scale -> scale_caps -> sink
            vp8depay.link(vp8dec)
            vp8dec.link(queue2)
            queue2.link(videoconvert)
            videoconvert.link(videoscale)
            videoscale.link(scale_capsfilter)
            scale_capsfilter.link(autovideosink)

            # Link the incoming pad to vp8depay
            sink_pad = vp8depay.get_static_pad("sink")
            pad.link(sink_pad)

            print("Created video pipeline: pad -> vp8depay -> vp8dec -> queue -> convert -> scale(1920x1080) -> sink")

        elif media_type == "audio" and encoding_name == "OPUS":
            # Create audio pipeline with proper synchronization
            stream_id = self.added_streams

            opusdepay = Gst.ElementFactory.make("rtpopusdepay", f"opusdepay_{stream_id}")
            opusdec = Gst.ElementFactory.make("opusdec", f"opusdec_{stream_id}")
            audioconvert = Gst.ElementFactory.make("audioconvert", f"audioconvert_{stream_id}")
            audioresample = Gst.ElementFactory.make("audioresample", f"audioresample_{stream_id}")
            autoaudiosink = Gst.ElementFactory.make("autoaudiosink", f"autoaudiosink_{stream_id}")

            # Configure audio sink
            autoaudiosink.set_property("sync", True)

            # Add elements to pipeline
            elements = [opusdepay, opusdec, audioconvert, audioresample, autoaudiosink]
            for element in elements:
                if self.pipe is not None:
                    self.pipe.add(element)
                element.sync_state_with_parent()

            # Link elements
            opusdepay.link(opusdec)
            opusdec.link(audioconvert)
            audioconvert.link(audioresample)
            audioresample.link(autoaudiosink)

            # Link the incoming pad
            sink_pad = opusdepay.get_static_pad("sink")
            pad.link(sink_pad)

            print(
                "Created audio pipeline: pad -> opusdepay -> queue -> opusdec -> queue -> convert -> resample -> sink"
            )

        else:
            print(f"Unsupported stream type: {media_type}/{encoding_name}")

        Gst.debug_bin_to_dot_file(self.pipe, Gst.DebugGraphDetails.ALL, f"pipeline_graph_{self.added_streams}")

        async def delayed_snapshot(pipe: Gst.Pipeline, name: str, delay: float = 5.0) -> None:
            await asyncio.sleep(delay)
            print("Taking DELAYEDsnapshot")
            Gst.debug_bin_to_dot_file(pipe, Gst.DebugGraphDetails.ALL, name)

        # inside your GLib callback:
        asyncio.run_coroutine_threadsafe(
            delayed_snapshot(self.pipe, f"pipeline_graph_delayed{self.added_streams}", 10.0), self.loop
        )
        self.added_streams += 1

        # Force latency recalculation after adding new stream
        # GLib.timeout_add(100, lambda: self.pipe.recalculate_latency() or False)

    def on_negotiation_needed(self, element: GstWebRTC.WebRTCBin) -> None:
        print("Negotiation needed")
        if self.added_data_channel:
            print("Data channel already added")
            return
        self.added_data_channel = True
        if self.webrtc is None:
            print("Error: WebRTC not initialized")
            return
        self.data_channel = self.webrtc.emit("create-data-channel", "chat", None)
        if self.data_channel:
            print("Data channel created on robot")
            self.data_channel.connect("on-message-string", self.on_message_string)

        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, None)
        if self.webrtc is not None:
            self.webrtc.emit("create-offer", None, promise)

    def on_offer_created(self, promise: Gst.Promise, _: GstWebRTC.WebRTCBin, __: None) -> None:
        print("on offer created")
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value("offer")
        print("offer:", offer)
        if self.webrtc is not None:
            self.webrtc.emit("set-local-description", offer, Gst.Promise.new())
        text = offer.sdp.as_text()
        print("offertext:", text)
        message = json.dumps({"sdp": {"type": "offer", "sdp": text}})
        if self.ws is not None:
            asyncio.run_coroutine_threadsafe(self.ws.send(message), self.loop)

    def send_ice_candidate_message(self, _: GstWebRTC.WebRTCBin, mlineindex: int, candidate: str) -> None:
        message = json.dumps({"ice": {"candidate": candidate, "sdpMLineIndex": mlineindex}})
        if self.ws is not None:
            asyncio.run_coroutine_threadsafe(self.ws.send(message), self.loop)

    def handle_client_message(self, message: str) -> None:
        print("Handling client message")
        print(message)
        msg = json.loads(message)
        msg_type = msg.get("type", None)
        msg_cameras = msg.get("cameras", [0])
        msg_audio = msg.get("audio", True)
        msg_undistort = msg.get("undistort", False)
        if "sdp" in msg and msg["sdp"]["type"] == "answer":
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
            if self.pipe:
                self.close_pipeline()

            self.start_pipeline(msg_cameras, msg_audio, msg_undistort)

            return

    async def websocket_handler(self, ws: websockets.WebSocketServerProtocol) -> None:
        print("Client connected")
        self.ws = ws
        async for msg in ws:
            print("Received message:", msg)
            self.handle_client_message(msg)
        print("Client disconnected")
        self.close_pipeline()


async def main() -> None:
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="WebRTC Video Streaming Server")
    parser.add_argument("--flip", action="store_true", help="Vertically flip the video stream")
    args = parser.parse_args()

    loop = asyncio.get_running_loop()
    server = WebRTCServer(loop, flip_video=args.flip)

    async def handler(websocket: websockets.WebSocketServerProtocol) -> None:
        await server.websocket_handler(websocket)

    asyncio.create_task(glib_main_loop_iteration())
    async with websockets.serve(handler, "0.0.0.0", 8765):
        print("WebSocket server running on ws://0.0.0.0:8765")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
