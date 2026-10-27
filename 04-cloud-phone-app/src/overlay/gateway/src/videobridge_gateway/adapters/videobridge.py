"""The emulator's Video Bridge (gRPC Rtc service): one WebRTC stream per
signalling session, JSEP messages both ways as text."""

from ..proto import ice_config_pb2 as ice
from ..proto import rtc_service_v2_pb2 as rtc
from ..proto import rtc_service_v2_pb2_grpc as rtc_grpc


class Bridge:
    def __init__(self, channel, metadata):
        self.stub = rtc_grpc.RtcStub(channel)
        self.metadata = metadata

    async def open(self, stun):
        """A new stream with this ICE server; its id (guid)."""
        ice_config = ice.IceServerConfig()
        stun_server = ice_config.ice_servers.add()
        stun_server.urls.append(stun)
        response = await self.stub.RequestRtcStream(rtc.RtcStreamRequest(ice_server_config=ice_config),
                                                    metadata=self.metadata, timeout=10)
        return response.id.guid

    async def messages(self, guid):
        """The stream's JSEP messages from the emulator, as texts."""
        request = rtc.ReceiveJsepMessageRequest(id=rtc.Id(guid=guid))
        async for response in self.stub.ReceiveJsepMessageStream(request, metadata=self.metadata):
            yield response.jsep_msg.message

    async def send(self, guid, text):
        """One JSEP message to the emulator."""
        request = rtc.SendJsepMessageRequest()
        request.jsep_msg.id.guid = guid
        request.jsep_msg.message = text
        await self.stub.SendJsepMessage(request, metadata=self.metadata, timeout=5)
