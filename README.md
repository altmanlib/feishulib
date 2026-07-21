# feishu-im-client

An asynchronous, typed client for selected Feishu IM REST operations and long-connection events. It has no runtime dependency on `lark_oapi`.

```python
from feishu_im import FeishuClient, FeishuConfig

config = FeishuConfig(app_id="cli_x", app_secret="secret")
async with FeishuClient(config) as client:
    await client.send_text("oc_chat", "hello")
```

Supported REST calls include sending, replying to, updating and deleting messages, downloading message resources, and looking up bot identity. Event handling currently supports text-message reception and card actions.

Never put an operator identity in card action values: handlers must trust only `CardActionEvent.operator`.
