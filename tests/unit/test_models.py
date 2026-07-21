import json

from feishu_im.models import CardActionResponse, OutboundMessage, Toast


def test_outbound_message_serializes_structured_content_once() -> None:
    message = OutboundMessage(
        receive_id="oc_chat",
        receive_id_type="chat_id",
        msg_type="text",
        content={"text": "你好"},
        uuid="request-1",
    )

    payload = message.to_payload()

    assert payload["receive_id"] == "oc_chat"
    assert payload["msg_type"] == "text"
    assert json.loads(str(payload["content"])) == {"text": "你好"}
    assert payload["uuid"] == "request-1"


def test_card_action_response_omits_absent_sections() -> None:
    response = CardActionResponse(toast=Toast(kind="success", content="Done"))

    assert response.to_payload() == {"toast": {"type": "success", "content": "Done"}}
