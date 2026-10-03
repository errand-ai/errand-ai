Requested official URL: https://opencode.ai/v2/docs/api
Accessed UTC: 2026-10-03T15:02:59.972004+00:00
Title: API | OpenCode
Retrieval: documentation extraction; excerpt may be abbreviated. Not a runtime test. Trailing whitespace normalized.

# API | OpenCode
URL: https://opencode.ai/v2/docs/api/

API | OpenCode

Esc

Start typing to search the documentation.

get`/api/health` Check server health

Report the owning server process and its application status.

Operation ID`v2.health.get`

### Responses

`200` ServiceHealth

`application/json` ServiceHealth

`400` InvalidRequestError

`application/json` InvalidRequestErrorEncoded

`401` UnauthorizedError

`application/json` UnauthorizedErrorEncoded

get`/api/server` Get server information

Return the URLs that can be used to connect to this server.

Operation ID`v2.server.get`

### Responses

`200` Success

`application/json`

`object`

`urls`

`string[]` required

Items

`string`

`400` InvalidRequestError

`application/json` InvalidRequestErrorEncoded

`401` UnauthorizedError

`application/json` UnauthorizedErrorEncoded

get`/api/location` Get location

Resolve the requested location or the server default location.

Operation ID`v2.location.get`

### Parameters

| Name | Location | Type | Description |
| --- | --- | --- | --- |
| `location` | query | `object | null` `object` `directory` `string | null` `string` or `null` `workspace` `string | null` `string` or `null` or `null` | No description |

### Responses

`200` Location.Info

`application/json` Location.InfoEncoded

`400` InvalidRequestError

`application/json` InvalidRequestErrorEncoded

`401` UnauthorizedError

`application/json` UnauthorizedErrorEncoded

get`/api/agent` List agents

Retrieve currently registered agents.

Operation ID`v2.agent.list`

### Parameters

| Name | Location | Type | Description |
| --- | --- | --- | --- |
| `location` | query | `object | null` `object` `directory` `string | null` `string` or `null` `workspace` `string | null` `string` or `null` or `null` | No description |

### Responses

`200` Success

`application/json`

`object`

`location` Location.InfoEncoded

`data`

`Agent.Info[]` required

ItemsAgent.Info

`400` InvalidRequestError

`application/json` InvalidRequestErrorEncoded

`401` UnauthorizedError

`application/json` UnauthorizedErrorEncoded

get`/api/agent/{agentID}` Get agent

Retrieve a single currently registered agent.

Operation ID`v2.agent.get`

### Parameters

| Name | Location | Type | Description |
| --- | --- | --- | --- |
| `agentID` required | path | `string` | No description |
| `location` | query | `object | null` `object` `directory` `string | null` `string` or `null` `workspace` `string | null` `string` or `null` or `null` | No description |

### Responses

`200` Success

`application/json`

`object`

`location` Location.InfoEncoded

`data` Agent.Info

`400` InvalidRequestError

`application/json` InvalidRequestErrorEncoded

`401` UnauthorizedError

`application/json` UnauthorizedErrorEncoded

`404` AgentNotFoundError

`application/json` AgentNotFoundErrorEncoded

get`/api/plugin` List plugins

Retrieve enabled server plugins and their current status.

Operation ID`v2.plugin.list`

### Parameters

| Name | Location | Type | Description |
| --- | --- | --- | --- |
| `location`
