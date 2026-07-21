# Issue: Preserve security-relevant event metadata and resource metadata

## 背景

当前 `feishulib` 已覆盖主要 REST API 和长连接能力，但事件解析阶段丢失了一些通用 SDK 应保留的协议字段，导致下游无法可靠完成事件新鲜度校验和文件资源处理

本 issue 只讨论 SDK 的通用数据暴露能力，不要求 SDK 承担下游业务策略

## 问题一：事件时间未暴露

当前 `MessageEvent` 和 `CardActionEvent` 没有暴露事件创建时间

schema 2.0 的 `header` 中包含 `create_time`，但 `parse_event_payload()` 解析后未保留

下游目前需要拒绝超过时间窗口的事件，例如：

- 重放的消息事件；
- 过期的卡片审核回调；
- 网络延迟后才到达的旧事件

如果 SDK 不提供原始事件时间，下游只能使用接收时间，无法区分“刚收到的旧事件”和“刚产生的新事件”。这会削弱幂等和安全边界

### 建议改动

为两个事件 DTO 增加统一字段：

```python
create_time: datetime | None
```

建议：

- 从 `header.create_time` 解析；
- 使用带时区的 UTC `datetime`；
- 对缺失或格式非法的字段保持明确行为：要么抛出 `FeishuEventParseError`，要么返回 `None`，需要在文档中说明；
- 保留现有 `event_id`、身份和消息字段行为不变

如果为了兼容已有调用方不希望立即改变构造参数，可以考虑新增属性或在末尾增加默认值字段

## 问题二：消息资源元数据未暴露

当前 `MessageEvent` 对文件消息只暴露：

```python
file_key: str | None
```

但没有文件名、MIME 类型或资源类型。下游的文件导入通常需要在下载后执行：

- 扩展名白名单校验；
- MIME 类型校验；
- 文件类型校验；
- 文本/二进制判断

如果飞书的原始事件本身不提供文件名和 MIME 类型，SDK 不应伪造这些字段；但应至少保留原始事件内容，或提供明确的资源元数据查询能力

### 建议改动

请先确认 Feishu `im.message.receive_v1` 文件消息实际能提供哪些字段，然后选择以下方案之一：

1. 在 `MessageEvent` 中增加可选字段：

   ```python
   file_name: str | None
   file_type: str | None
   mime_type: str | None
   ```

2. 如果事件不含这些字段：
   - 保留可安全使用的原始消息内容；
   - 在 `FeishuClient` 增加资源元数据查询方法，或在 `download_file()` 返回元数据；
   - 文档明确说明字段来源和可靠性

不要根据 `file_key` 推断文件名或 MIME 类型

## 问题三：原始协议字段的扩展能力

当前事件 DTO 是严格、精简的模型，这是合理的；但事件协议字段可能随飞书版本扩展。建议提供一种受控的扩展方式，例如：

```python
raw_header: Mapping[str, JsonValue]
raw_event: Mapping[str, JsonValue]
```

或者至少保留安全相关但暂时未建模的字段

要求：

- 不在日志中输出完整 payload；
- 原始字段仍然视为不可信输入；
- 文档说明原始字段不能作为身份认证依据；
- 不影响现有 typed API 的使用体验

## 不属于 SDK 的职责

以下内容不应由 `feishulib` 固化：

- 事件是否超过五分钟；
- 用户是否有贡献者/审核人权限；
- 提交人是否可以审核自己的内容；
- 允许 `.md` / `.txt` 还是其他文件格式；
- 业务事件去重和数据库落库；
- 卡片按钮对应的业务状态机

SDK 只需要提供完整、可信、类型明确的协议数据

## Acceptance Criteria

- [ ] `MessageEvent` 可以获得事件创建时间
- [ ] `CardActionEvent` 可以获得事件创建时间
- [ ] 时间解析使用 UTC aware `datetime`，并有单元测试覆盖秒/毫秒格式（如协议支持）
- [ ] 文件消息的资源字段来源有明确测试和文档说明
- [ ] 如果飞书事件不提供文件名/MIME，SDK 不伪造值，并提供原始字段或资源元数据查询方案
- [ ] malformed/unsupported event 的现有安全行为不被放宽
- [ ] 现有 REST、WebSocket、重试和 token 刷新测试继续通过
- [ ] 公共 API 的兼容性影响在 CHANGELOG 或 release notes 中说明

## 下游适配说明

下游仍会通过 adapter 负责：

- `MessageReceipt.message_id` 到内部字符串接口的转换；
- SDK 异常到业务异常的映射；
- `FeishuWebSocket.run_forever()` 的任务生命周期管理；
- 事件时间窗口、权限和业务校验
