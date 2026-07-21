# Long Connection Protocol

The client discovers a `wss` endpoint with `POST /callback/ws/endpoint` and uses its own minimal protobuf `Frame` schema. Field numbers match Feishu's long-connection wire protocol.

Control `ping` and `pong` frames maintain liveness. Data frames are sent to the event channel and acknowledged with a data response whose `biz_rt` header contains handler runtime in milliseconds.
