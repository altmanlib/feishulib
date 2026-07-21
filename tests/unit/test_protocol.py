from pathlib import Path

from feishu_im.protocol import FrameMethod, WireFrame, decode_frame, encode_frame, make_ping


def test_ping_frame_matches_static_feishu_wire_fixture() -> None:
    expected = bytes.fromhex(Path("tests/fixtures/ping_frame.hex").read_text().strip())
    assert encode_frame(make_ping(7)) == expected


def test_decoder_reads_required_headers_and_payload() -> None:
    frame = WireFrame(12, 34, 7, FrameMethod.DATA, {"message_id": "m_1", "type": "event"}, b'{"schema":"2.0"}')
    assert decode_frame(encode_frame(frame)) == frame
