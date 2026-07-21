# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportUnknownArgumentType=false
"""Pythonic facade for Feishu long-connection protobuf frames."""

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType

from google.protobuf.message import DecodeError, EncodeError

from feishu_im.exceptions import FeishuProtocolError
from feishu_im.models import JsonValue
from feishu_im.proto import frame_pb2


class FrameMethod(IntEnum):
    CONTROL = 0
    DATA = 1


@dataclass(frozen=True, slots=True)
class WireFrame:
    sequence_id: int
    log_id: int
    service_id: int
    method: FrameMethod
    headers: Mapping[str, str]
    payload: bytes = b""
    payload_encoding: str | None = None
    payload_type: str | None = None
    log_id_new: str | None = None


def encode_frame(frame: WireFrame) -> bytes:
    """Serialize a validated frame into Feishu-compatible protobuf bytes."""
    if not 0 <= frame.sequence_id <= 2**64 - 1 or not 0 <= frame.log_id <= 2**64 - 1:
        raise FeishuProtocolError("frame IDs must fit uint64")
    if not -(2**31) <= frame.service_id < 2**31 or not -(2**31) <= int(frame.method) < 2**31:
        raise FeishuProtocolError("service and method must fit int32")
    message = frame_pb2.Frame(seq_id=frame.sequence_id, log_id=frame.log_id, service=frame.service_id, method=int(frame.method))
    for key, value in frame.headers.items():
        header = message.headers.add()
        header.key = key
        header.value = value
    if frame.payload_encoding is not None:
        message.payload_encoding = frame.payload_encoding
    if frame.payload_type is not None:
        message.payload_type = frame.payload_type
    if frame.payload:
        message.payload = frame.payload
    if frame.log_id_new is not None:
        message.log_id_new = frame.log_id_new
    try:
        return message.SerializeToString()
    except EncodeError as error:
        raise FeishuProtocolError("could not encode protobuf frame") from error


def decode_frame(data: bytes) -> WireFrame:
    """Decode and validate a compatible protobuf frame."""
    message = frame_pb2.Frame()
    try:
        message.ParseFromString(data)
    except DecodeError as error:
        raise FeishuProtocolError("invalid protobuf frame") from error
    if not message.IsInitialized():
        raise FeishuProtocolError("protobuf frame is missing required fields")
    try:
        method = FrameMethod(message.method)
    except ValueError as error:
        raise FeishuProtocolError("unknown frame method") from error
    headers: dict[str, str] = {}
    for header in message.headers:
        if header.key in headers:
            raise FeishuProtocolError("duplicate frame header")
        headers[header.key] = header.value
    return WireFrame(
        message.seq_id,
        message.log_id,
        message.service,
        method,
        MappingProxyType(headers),
        message.payload,
        message.payload_encoding if message.HasField("payload_encoding") else None,
        message.payload_type if message.HasField("payload_type") else None,
        message.log_id_new if message.HasField("log_id_new") else None,
    )


def make_ping(service_id: int) -> WireFrame:
    """Build a control ping frame."""
    return WireFrame(0, 0, service_id, FrameMethod.CONTROL, {"type": "ping"})


def make_data_response(
    request: WireFrame,
    *,
    status_code: int,
    result_payload: Mapping[str, JsonValue] | None,
    business_runtime_ms: int,
) -> WireFrame:
    """Build the ACK frame for an incoming data event."""
    headers = dict(request.headers)
    headers["biz_rt"] = str(business_runtime_ms)
    body: dict[str, JsonValue] = {"code": status_code}
    if result_payload is not None:
        encoded = json.dumps(dict(result_payload), ensure_ascii=False, separators=(",", ":")).encode()
        body["data"] = base64.b64encode(encoded).decode()
    return WireFrame(request.sequence_id, request.log_id, request.service_id, request.method, headers, json.dumps(body, separators=(",", ":")).encode())
