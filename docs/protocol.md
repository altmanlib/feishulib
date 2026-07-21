# Long Connection Protocol

The client discovers a `wss` endpoint with `POST /callback/ws/endpoint` and uses its own minimal protobuf `Frame` schema. Field numbers match Feishu's long-connection wire protocol.

Control `ping` and `pong` frames maintain liveness. Data frames are sent to the event channel and acknowledged with a data response whose `biz_rt` header contains handler runtime in milliseconds.

## Event ACK policy

A valid event handled successfully is acknowledged with code `200`. Events that cannot be parsed as a supported schema 2.0 event are permanent input failures: the client acknowledges them with code `200` and does not dispatch them. Handler failures and queue saturation are acknowledged with code `503`; handler timeout is acknowledged with code `500`.
