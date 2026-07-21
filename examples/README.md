# Examples

All scripts read `FEISHU_APP_ID` and `FEISHU_APP_SECRET` from `.env`.

| Capability | Script | Extra variables |
| --- | --- | --- |
| Bot identity | `bot_identity.py` | None |
| Send generic message / `send_message` | `send_message.py` | `FEISHU_RECEIVE_ID`, optional `FEISHU_TEXT`, `FEISHU_RECEIVE_ID_TYPE` |
| Send text | `send_text.py` | `FEISHU_RECEIVE_ID`, optional `FEISHU_TEXT`, `FEISHU_RECEIVE_ID_TYPE` |
| Send card / `send_card` | `send_card.py` | `FEISHU_RECEIVE_ID`, optional `FEISHU_RECEIVE_ID_TYPE` |
| Reply / `reply_message` | `reply_message.py` | `FEISHU_MESSAGE_ID`, optional `FEISHU_TEXT` |
| Reply text | `reply_text.py` | `FEISHU_MESSAGE_ID`, optional `FEISHU_TEXT` |
| Update / `update_message` | `update_message.py` | `FEISHU_MESSAGE_ID` |
| Update card | `update_card.py` | `FEISHU_MESSAGE_ID` |
| Delete / `delete_message` | `delete_message.py` | `FEISHU_MESSAGE_ID`, `FEISHU_CONFIRM_DELETE=yes` |
| Download resource | `download_resource.py` | `FEISHU_MESSAGE_ID`, `FEISHU_FILE_KEY`, optional `FEISHU_RESOURCE_TYPE`, `FEISHU_OUTPUT_PATH` |
| Receive messages | `chat_bot.py` | Configure `im.message.receive_v1` long-connection subscription |
| Card actions | `card_action_bot.py` | Configure `card.action.trigger` long-connection subscription |

Run an example from the project root, for example:

```bash
uv run python examples/send_text.py
```
