import asyncio, json, os
import websockets
import logging
from azure.iot.device.aio import IoTHubDeviceClient
from azure.iot.device import MethodResponse

HA_WS_URL = os.getenv("HA_WS_URL", "ws://supervisor/core/websocket")
SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN")
IOTHUB_CONN_STR = os.getenv("IOTHUB_DEVICE_CONNECTION_STRING")
IOTHUB_METHOD_NAME = os.getenv("IOTHUB_METHOD_NAME", "ha.call")

_LOGGER = logging.getLogger(__name__)

class HAWebSocket:
    def __init__(self, url, token):
        self._url = url
        self._token = token
        self._ws = None
        self._lock = asyncio.Lock()
        self._next_id = 1

    async def _ensure(self):

        if self._ws is not None:
            
            closed = getattr(self._ws, "closed", False)
            
            if not closed:
                return
        
        self._ws = await websockets.connect(self._url)
        hello = json.loads(await self._ws.recv())
        
        if hello.get("type") != "auth_required":
            raise RuntimeError("Unexpected handshake from HA")
        
        await self._ws.send(json.dumps({"type": "auth", "access_token": self._token}))
        
        auth_ok = json.loads(await self._ws.recv())
        
        if auth_ok.get("type") != "auth_ok":
            raise RuntimeError(f"Auth failed to HA: {auth_ok}")
        
        self._next_id = 1

    async def send_and_recv(self, msg: dict, timeout: float = 10.0):
        async with self._lock:

            await self._ensure()

            # Ensure monotonically increasing id
            if "id" in msg and isinstance(msg["id"], int) and msg["id"] >= self._next_id:
                self._next_id = msg["id"] + 1
            else:
                msg["id"] = self._next_id
                self._next_id += 1

            try:
                _LOGGER.info("Logging: HA WS: sending message: %s", msg)
                await self._ws.send(json.dumps(msg))
            
            except Exception:
                _LOGGER.warning("Logging: HA WS: send failed, reconnecting", exc_info=True)
                self._ws = None
                await self._ensure()
                await self._ws.send(json.dumps(msg))

            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            _LOGGER.info("Logging: HA WS: received response: %s", raw)

            return raw

async def run_bridge():

    #Check Supervisor Token
    if not SUPERVISOR_TOKEN:
        _LOGGER.error("Logging: SUPERVISOR_TOKEN is not set!")
        return

    #Check Connection String
    if not IOTHUB_CONN_STR:
        _LOGGER.error("Logging: Env var IOTHUB_DEVICE_CONNECTION_STRING is not set!")
        return
    else:
        try:
            parts = dict(p.split("=", 1) for p in IOTHUB_CONN_STR.split(";") if "=" in p)
            _LOGGER.info(
                "Logging: IoT Hub connection: HostName=%s, DeviceId=%s",
                parts.get("HostName"),
                parts.get("DeviceId"),
            )
        except Exception:
            _LOGGER.warning("Logging: Could not parse IoT Hub connection string for logging")

    _LOGGER.info("Logging: Creating IoTHubDeviceClient…")
    #End Check Connection String

    device_client = IoTHubDeviceClient.create_from_connection_string(
        IOTHUB_CONN_STR,
        websockets=True
    )

    _LOGGER.info("Logging: Connecting to IoT Hub")
    await device_client.connect()
    _LOGGER.info("Logging: Connected to IoT Hub")

    ha = HAWebSocket(HA_WS_URL, SUPERVISOR_TOKEN)

    async def on_method(request):
        
        _LOGGER.info("Logging: IoT Hub: received direct method '%s' with payload: %s", request.name, request.payload)

        if request.name != IOTHUB_METHOD_NAME:
            resp = MethodResponse.create_from_method_request(request, 404, {"error":"unknown method"})
            await device_client.send_method_response(resp)
            return

        try:
            payload = request.payload or {}
            msg = payload.get("message")
            if not isinstance(msg, dict):
                raise ValueError("payload.message must be an object")

            timeout = (payload.get("timeout_ms") or 10000) / 1000.0
            raw = await ha.send_and_recv(msg, timeout=timeout)
            ha_resp = json.loads(raw)
            status = 200 if ha_resp.get("success", True) else 500

            resp = MethodResponse.create_from_method_request(
                request, status, {"status": status, "result": ha_resp}
            )

        except asyncio.TimeoutError:
            resp = MethodResponse.create_from_method_request(
                request, 504, {"error": "HA timeout"}
            )

        except Exception as ex:
            resp = MethodResponse.create_from_method_request(
                request, 500, {"error": str(ex)}
            )

        _LOGGER.info(
            "Logging: IoT Hub: sending method response, status=%s, payload=%s",
            getattr(resp, "status", None),
            getattr(resp, "payload", None),
        )
        
        await device_client.send_method_response(resp)

    device_client.on_method_request_received = on_method

    try:
        while True:
            await asyncio.sleep(60)
    finally:
        await device_client.shutdown()

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    _LOGGER.info("Logging: Starting Azure IoT Hub Connection")

    asyncio.run(run_bridge())