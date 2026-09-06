"""Z1 adapter using python-roborock 4.8.0 authentication and transport.

The raw product endpoint follows that version's get_home_data_v3 implementation.
It intentionally avoids HomeDataProduct's unsupported category conversion, without
patching any shared SDK classes or pretending the dryer is a washing machine.
"""

import asyncio
import json
from importlib.metadata import version

from roborock.data import HomeDataDevice, UserData
from roborock.devices.rpc.a01_channel import send_decoded_command
from roborock.devices.transport.mqtt_channel import create_mqtt_channel
from roborock.mqtt.roborock_session import create_lazy_mqtt_session
from roborock.protocol import create_mqtt_params
from roborock.protocols.a01_protocol import decode_rpc_response
from roborock.web_api import PreparedRequest, RoborockApiClient, _get_hawk_authentication

from .protocol import FIELDS, START_FIELDS, MODELS, validate_schema, validate_values, supports_start, start_payload


class ReadOnlyClient:
    def __init__(self, data, http_session):
        if version("python-roborock") != "4.8.0":
            raise ValueError("This adapter requires review before changing python-roborock 4.8.0")
        self.user = UserData.from_dict(data["user_data"])
        self.api = RoborockApiClient(data["username"], base_url=data["base_url"], session=http_session)
        self.http_session = http_session
        self.session = None
        self.devices = {}
        self.channels = {}
        self.locks = {}
        self.last_start = {}
        self.push_callback = None
        self.unsubscribers = []

    async def setup(self):
        async with asyncio.timeout(25):
            # SDK authentication/signing; no local cryptography or token copies.
            home_id = await self.api._get_home_id(self.user)
            path = "/v3/user/homes/" + str(home_id)
            rriot = self.user.rriot
            if not rriot.r.a:
                raise ValueError("Account API endpoint missing")
            request = PreparedRequest(rriot.r.a, self.http_session,
                                      {"Authorization": _get_hawk_authentication(rriot, path)})
            response = await request.request("get", path)
            if not response.get("success") or not isinstance(response.get("result"), dict):
                raise ValueError("Device discovery failed; check source Roborock account")
            home = response["result"]
            products = {p["id"]: p for p in home.get("products", [])}
            params = create_mqtt_params(rriot)
            self.session = await create_lazy_mqtt_session(params)
            for raw in home.get("devices", []) + home.get("receivedDevices", []):
                product = products.get(raw.get("productId"), {})
                model = product.get("model")
                if model not in MODELS:
                    continue
                validate_schema(product)
                if raw.get("pv") != "A01":
                    raise ValueError("Unexpected device protocol")
                device = HomeDataDevice.from_dict(raw)
                self.devices[device.duid] = {"model": model, "name": MODELS[model], "firmware": raw.get("fv"),
                                              "supports_start": supports_start(product)}
                self.locks[device.duid] = asyncio.Lock()
                self.channels[device.duid] = create_mqtt_channel(self.user, params, self.session, device)
                self.unsubscribers.append(await self.channels[device.duid].subscribe(
                    lambda message, did=device.duid: self._handle_push(did, message)))
            if not self.devices:
                raise ValueError("No supported Z1 Max devices in source account")

    def _handle_push(self, device_id, message):
        try:
            decoded = decode_rpc_response(message)
        except Exception:
            return
        values = {int(k): v for k,v in decoded.items()
                  if int(k) in FIELDS and type(v) is int and v >= 0}
        if self.push_callback and values:
            self.push_callback(device_id, values)

    async def query(self, device_id):
        async with self.locks[device_id]:
            return await self._query(device_id)

    async def _query(self, device_id, control=False):
        async with asyncio.timeout(18):
            response = await send_decoded_command(
                self.channels[device_id], {10000: list(FIELDS) + (list(START_FIELDS) if control else [])}, value_encoder=json.dumps
            )
        values = validate_values(response)
        return {**values, **{k: response.get(k) for k in START_FIELDS}} if control else values

    async def start_current_program(self, device_id):
        if not self.devices[device_id]["supports_start"]:
            raise ValueError("设备启动字段不匹配，已禁止控制")
        async with self.locks[device_id]:
            loop = asyncio.get_running_loop()
            if loop.time() - self.last_start.get(device_id, float("-inf")) < 60:
                raise ValueError("60 秒内已请求过启动，请先查看设备是否运行")
            payload = start_payload(await self._query(device_id, control=True))
            # Record BEFORE transmission: a timeout may still mean the device started.
            self.last_start[device_id] = loop.time()
            async with asyncio.timeout(18):
                return await send_decoded_command(self.channels[device_id], payload, value_encoder=lambda value: value)

    async def close(self):
        self.push_callback = None
        for unsub in self.unsubscribers:
            unsub()
        self.unsubscribers.clear()
        if self.session is not None:
            await self.session.close()
            self.session = None
