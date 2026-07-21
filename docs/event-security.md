# Event Security Boundary

Only schema `2.0` events are accepted. `p2.im.message.receive_v1` and `p2.card.action.trigger` are the supported subscription types.

For card callbacks, the operator identity is taken exclusively from `event.operator`. Values in `event.action.value` are opaque user-controlled input and never contribute to the authenticated identity. Reject callbacks without `event.operator.open_id`.

Malformed and unsupported events are acknowledged and dropped without dispatch. The client may log the parse error and event type, but never logs the raw event payload, credentials, or action values.
