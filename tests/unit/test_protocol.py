from pathlib import Path

import pytest

from feishulib.exceptions import FeishuProtocolError
from feishulib.protocol import FrameMethod, WireFrame, decode_frame, encode_frame, make_data_response, make_ping


def test_ping_frame_matches_static_feishu_wire_fixture() -> None:
    expected = bytes.fromhex(Path("tests/fixtures/ping_frame.hex").read_text().strip())
    assert encode_frame(make_ping(7)) == expected


def test_decoder_reads_required_headers_and_payload() -> None:
    frame = WireFrame(12, 34, 7, FrameMethod.DATA, {"message_id": "m_1", "type": "event"}, b'{"schema":"2.0"}')
    assert decode_frame(encode_frame(frame)) == frame


def test_protocol_rejects_bad_frames_and_builds_data_response() -> None:
    with pytest.raises(FeishuProtocolError):
        decode_frame(b"\xff")
    with pytest.raises(FeishuProtocolError):
        encode_frame(WireFrame(-1, 0, 1, FrameMethod.DATA, {}))
    request = WireFrame(1, 2, 7, FrameMethod.DATA, {"type": "event"})
    response = make_data_response(request, status_code=200, result_payload={"ok": True}, business_runtime_ms=12)
    assert response.headers["biz_rt"] == "12"
    assert b'"data"' in response.payload
