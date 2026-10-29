# Agent 配置使用指南

## 1. 配置概述

myAgent 使用 YAML 文件管理不同 Agent 的配置。每个 Agent 对应一个独立配置文件，主要用于指定 Agent 的实现类、执行流程、模型服务、工具、技能、记忆和运行参数。

配置文件默认存放在 `data/agents/` 目录，例如：

```text
data/agents/
├── default.yaml
├── coder.yaml
└── planner.yaml
```

框架通过 `AgentConfig.from_yaml()` 加载配置，完成基础校验后，由 `AgentManager` 根据配置创建 Agent、Loop 和相关组件。

**配置原则：**

- 通用配置由 `AgentConfig` 统一管理。
- 不同 Agent 可以采用不同的模型、提示词、工具和技能。
- `agent_class` 和 `loop_class` 支持通过 Python 导入路径加载自定义类。
- `agent_options` 和 `loop_options` 用于扩展专属配置，避免修改通用配置结构。
- API Key 不直接写入 YAML，而是通过环境变量提供。

## 2. Agent 基本配置

| 参数 | 类型 | 是否必填 | 默认值 | 说明与可填内容 |
|---|---|---|---|---|
| `name` | `str` | 是 | 无 | Agent 实例名称，例如 `default`、`coder`、`planner`；不能为空 |
| `agent_class` | `str` | 否 | `myagent.core.my_agent.MyAgent` | Agent 实现类的完整 Python 导入路径 |
| `loop_class` | `str` | 否 | `myagent.core.loop.AgentLoop` | Loop 实现类的完整 Python 导入路径 |
| `system_prompt` | `str` | 是 | 无 | 系统提示词文件路径，例如 `prompts/coder.md` |
| `workspace` | `str` | 否 | `data/workspace/` | Agent 工作目录，用于存放运行过程中的工作文件 |

### 2.1 agent_class 与 loop_class

两个参数分别指定 Agent 和 Loop 的 Python 类，而不是 Python 源文件的磁盘路径。

例如：

```yaml
agent_class: myagent.core.my_agent.MyAgent
loop_class: myagent.core.loop.AgentLoop
```

如果需要使用自定义类：

```yaml
agent_class: myagent.extensions.planner_agent.PlannerAgent
loop_class: myagent.extensions.planner_loop.PlannerLoop
```

对应的 Python 类必须能够被正常导入，并分别继承 `BaseAgent` 和 `BaseAgentLoop`。

省略两个字段时，使用框架提供的默认实现。`AgentConfig` 负责校验导入路径格式，`AgentManager` 负责实际加载和检查继承关系。

### 2.2 路径约定

本项目约定：

- `system_prompt` 的相对路径以 `data/` 为基准，例如 `prompts/coder.md` 对应 `data/prompts/coder.md`。
- `workspace` 的相对路径以项目根目录为基准，例如 `projects/`。
- `agent_class`、`loop_class` 使用 Python 导入路径，不使用文件系统路径。

当前 `AgentConfig` 只保存路径字符串，不检查目标文件是否存在。实际路径解析由相关组件完成。

## 3. 模型配置（model）

`model` 是必填的字典配置，用于指定模型服务及其请求参数。

### 3.1 参数说明

| 参数 | 类型 | 是否必填 | 默认或允许取值 | 说明 |
|---|---|---|---|---|
| `provider` | `str` | 是 | `openai`、`anthropic`、`deepseek`、`ollama`、`lmstudio`、`vllm` 等 | 标识模型服务提供方，允许自定义非空名称 |
| `protocol` | `str` | 是 | `openai`、`anthropic` | 指定 API 兼容协议 |
| `model_name` | `str` | 是 | 模型服务支持的模型 ID | 实际请求的模型名称 |
| `base_url` | `str` 或 `null` | 否 | 不填写时使用对应 SDK 的默认地址 | 模型服务的 API 基础地址 |
| `api_key_env` | `str` 或 `null` | 否 | 例如 `OPENAI_API_KEY` | 存储 API Key 的环境变量名称 |
| `temperature` | 数值 | 否 | 例如 `0`、`0.7`、`1.0` | 控制模型生成的随机性，具体范围由模型决定 |
| `max_tokens` | 正整数 | 否 | 例如 `4096` | 限制模型输出 Token 数量 |
| `max_completion_tokens` | 正整数 | 否 | 例如 `4096` | OpenAI Chat Completions 的输出 Token 限制参数 |
| `timeout` | 数值 | 否 | `60`（当前 LLMClient 默认值） | 单次 API 请求的超时设置，单位为秒 |
| `max_retries` | 非负整数 | 否 | `2`（当前 LLMClient 默认值） | SDK 自动重试次数，不包含首次请求 |

其中，`provider`、`protocol`、`model_name` 必须为非空字符串。

**需要区分三个核心参数：**

- `provider` 表示使用哪一家模型服务，例如 DeepSeek、Ollama。
- `protocol` 决定 `LLMClient` 使用 OpenAI SDK 还是 Anthropic SDK。
- `model_name` 决定向服务器请求哪个具体模型。

当前 `LLMClient` 根据 `protocol` 选择 SDK，并根据 `base_url` 决定请求地址；`provider` 主要用于标识服务提供方，不直接决定客户端类型。

### 3.2 常见模型服务配置

| 服务 | provider | protocol | base_url 示例 |
|---|---|---|---|
| OpenAI | `openai` | `openai` | 可省略，使用官方 SDK 默认地址 |
| Anthropic | `anthropic` | `anthropic` | 可省略，使用官方 SDK 默认地址 |
| DeepSeek | `deepseek` | `openai` | `https://api.deepseek.com` |
| DeepSeek | `deepseek` | `anthropic` | `https://api.deepseek.com/anthropic` |
| Ollama（本地） | `ollama` | `openai` | `http://localhost:11434/v1` |
| LM Studio（本地） | `lmstudio` | `openai` | `http://localhost:1234/v1` |
| vLLM（本地） | `vllm` | `openai` | `http://localhost:8000/v1` |

表中是常见接入方式，并非完整支持列表。不同服务可能支持多种兼容协议，具体取决于所使用的服务版本。

`model_name` 必须填写服务端实际提供的模型 ID。例如，Ollama 可以使用 `qwen3:8b`，但需要预先下载对应模型。LM Studio 和 vLLM 则应使用各自服务返回的模型标识。

### 3.3 API Key 配置

`api_key_env` 填写的是**环境变量名称**，不是 API Key 本身。

例如：

```yaml
model:
  provider: deepseek
  protocol: openai
  model_name: deepseek-flash
  base_url: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY
```

对应的 `data/.env`：

```dotenv
DEEPSEEK_API_KEY=your_api_key
```

程序启动时，应先加载 `.env`，然后由 `LLMClient` 通过 `os.getenv()` 获取密钥。

对于无需身份验证的本地模型服务，可以省略 `api_key_env`。当前 `LLMClient` 对 localhost、127.0.0.1 和 ::1 上的服务支持使用占位密钥。

需要注意：本地地址不代表服务一定无需认证。如果本地模型服务启用了 API Key 验证，仍然需要正确配置 `api_key_env`。

### 3.4 模型生成参数

`temperature` 用于控制输出的随机性。一般来说，较低的值使输出更稳定，较高的值使输出更多样。但并非所有模型都支持该参数，具体取值范围应以模型服务文档为准。

`max_tokens` 和 `max_completion_tokens` 都用于控制输出长度，但对应的 API 参数不同。

按照当前 `LLMClient` 的实现：

- OpenAI 协议优先使用 `max_completion_tokens`，未配置时使用 `max_tokens`。
- Anthropic 协议使用 `max_tokens`；未配置时默认使用 `4096`。
- 某些模型可能不支持这些参数中的部分选项。

建议只配置当前模型实际支持的输出长度参数，避免同时填写产生歧义。

`timeout` 控制 API 请求超时，`max_retries` 控制 SDK 发生可重试错误时的自动重试次数。例如，`max_retries: 2` 最多意味着首次请求加两次重试。

## 4. Agent 能力配置

### 4.1 工具（tools）

| 参数 | 类型 | 默认值 | 可填内容 |
|---|---|---|---|
| `tools` | `list[str]` | `[]` | 已注册的工具名称，例如 `read_file`、`write_file`、`execute_shell`、`load_skill` |

示例：

```yaml
tools:
  - read_file
  - write_file
  - execute_shell
```

该列表决定当前 Agent 允许使用哪些工具。具体工具需要由 `ToolRegistry` 提供，工具执行由 `ToolExecutor` 负责。

配置为空列表表示不为该 Agent 配置工具。

### 4.2 技能（skills）

| 参数 | 类型 | 默认值 | 可填内容 |
|---|---|---|---|
| `skills` | `list[str]` | `[]` | 已安装 Skill 的名称，例如 `code_review` |

示例：

```yaml
skills:
  - code_review
```

Skill 名称应与框架能够发现的 Skill 对应。Skill 的实际加载过程由 `SkillLoader` 负责。

### 4.3 记忆（memory）

| 参数 | 类型 | 默认值 | 可填内容 |
|---|---|---|---|
| `memory.enabled` | `bool` | `false` | `true` 或 `false`，控制是否启用长期记忆 |
| `memory.files` | `list[str]` | `[]` | 需要预加载的记忆文件，例如 `MEMORY.md` |

示例：

```yaml
memory:
  enabled: true
  files:
    - MEMORY.md
```

`memory.files` 中的路径约定相对于 `data/.memory/`，具体文件读取由 `MemoryManager` 负责。

这里仅指定记忆功能的开关和文件列表，不定义记忆提取、更新或检索算法。

### 4.4 Hook（hooks）

| 参数 | 类型 | 默认值 | 可填内容 |
|---|---|---|---|
| `hooks` | `list[str]` | `[]` | 已注册的 Hook 名称 |

示例：

```yaml
hooks:
  - request_logger
  - tool_audit
```

上述名称仅用于展示配置格式，需要有对应 Hook 实现并完成注册后才能使用。

Hook 的触发时机和执行行为由 `HookManager` 决定，而不是由 YAML 字段本身决定。

## 5. 运行控制配置

| 参数 | 类型 | 默认值 | 允许范围 | 说明 |
|---|---|---|---|---|
| `max_steps` | `int` | `20` | ≥ 1 | 单次 Agent 执行允许的最大 Loop 步数 |
| `max_tool_calls` | `int` | `30` | ≥ 0 | 单次 Agent 执行允许的最大工具调用次数 |
| `max_context_tokens` | `int` | `32000` | ≥ 1 | Agent 的上下文 Token 预算 |
| `auto_compact` | `bool` | `true` | `true`、`false` | 是否允许自动压缩上下文 |

示例：

```yaml
max_steps: 20
max_tool_calls: 30
max_context_tokens: 32000
auto_compact: true
```

`max_steps` 由 `AgentLoop` 执行过程检查，`max_tool_calls` 用于限制工具调用次数。需要注意，Loop 步数与工具调用次数并不完全相同，一次模型响应可能包含多个工具调用。

`max_context_tokens` 是框架内部的上下文预算，不代表模型服务的真实最大上下文窗口。实际配置不能超过模型支持的上下文能力。

`auto_compact` 由上下文管理模块使用。即使设置为 `true`，也需要 `ContextCompactor` 实现相应逻辑后才会生效。

这些字段由 `AgentConfig` 校验，但实际限制必须由对应运行模块执行。

## 6. 自定义扩展配置

为支持未来新增的 Agent 和 Loop，框架提供两个扩展字段。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `agent_options` | `dict[str, Any]` | `{}` | 具体 Agent 的专属配置 |
| `loop_options` | `dict[str, Any]` | `{}` | 具体 Loop 的专属配置 |

例如：

```yaml
agent_options:
  max_plan_steps: 10
  require_review: true

loop_options:
  max_revisions: 3
```

`AgentConfig` 不预先规定扩展字段的名称和内容，而是将它们交给具体 Agent 和 Loop 校验。

例如，`PlannerAgent` 可以使用 `PlannerOptions(BaseModel)` 定义规划步数和审核开关；`PlannerLoop` 可以使用单独的 Pydantic 模型校验最大修订次数。

这样，在新增 Agent 或 Loop 时，不需要不断修改通用配置类。

## 7. 完整配置示例

### 7.1 示例一：使用 DeepSeek 云端模型

文件：`data/agents/coder.yaml`

```yaml
name: coder
agent_class: myagent.core.my_agent.MyAgent
loop_class: myagent.core.loop.AgentLoop

model:
  provider: deepseek
  protocol: openai
  model_name: deepseek-flash
  base_url: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY
  temperature: 0.7
  max_tokens: 4096
  timeout: 60
  max_retries: 2

system_prompt: prompts/coder.md

tools:
  - read_file
  - write_file
  - execute_shell
  - load_skill

skills:
  - code_review

memory:
  enabled: true
  files:
    - MEMORY.md

hooks: []

max_steps: 20
max_tool_calls: 30
max_context_tokens: 32000
auto_compact: true
workspace: data/workspace/

agent_options: {}
loop_options: {}
```

该配置适合普通代码辅助 Agent，使用 DeepSeek 的 OpenAI 兼容接口调用模型。

### 7.2 示例二：使用 Ollama 本地模型

文件：`data/agents/local.yaml`

```yaml
name: local

model:
  provider: ollama
  protocol: openai
  model_name: qwen3:8b
  base_url: http://localhost:11434/v1
  temperature: 0.7
  max_tokens: 4096

system_prompt: prompts/base.md

tools:
  - read_file

max_steps: 10
workspace: data/workspace/
```

该示例省略了 `agent_class` 和 `loop_class`，因此使用默认的 `MyAgent` 与 `AgentLoop`。

使用前需要启动 Ollama 服务，并确保服务端已经安装 `qwen3:8b` 模型。由于本地 Ollama 默认不要求 API Key，因此无需填写 `api_key_env`。

### 7.3 示例三：自定义 PlannerAgent 和 PlannerLoop

文件：`data/agents/planner.yaml`

```yaml
name: planner

agent_class: myagent.extensions.planner_agent.PlannerAgent
loop_class: myagent.extensions.planner_loop.PlannerLoop

model:
  provider: anthropic
  protocol: anthropic
  model_name: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY
  max_tokens: 4096

system_prompt: prompts/planner.md

tools:
  - read_file
  - write_file

max_steps: 30

agent_options:
  max_plan_steps: 10
  require_review: true

loop_options:
  max_revisions: 3
```

该示例展示了通过 Python 导入路径加载扩展组件，以及通过 `agent_options`、`loop_options` 配置专属参数的方法。

新增 `PlannerAgent` 和 `PlannerLoop` 后，无需修改 `AgentConfig` 的字段结构，也不需要向 `AgentManager` 增加固定类型映射。

## 8. 配置加载与校验

通过 `AgentConfig.from_yaml()` 加载配置：

```python
from myagent.core.config import AgentConfig

config = AgentConfig.from_yaml("data/agents/coder.yaml")

print(config.name)
print(config.model["model_name"])
print(config.agent_class)
print(config.tools)
```

`AgentConfig` 负责以下校验：

- 顶层 YAML 必须是映射对象，不允许出现未定义的顶层字段。
- `name`、`model`、`system_prompt` 必须填写。
- `agent_class`、`loop_class` 必须符合 Python 导入路径的基本格式。
- `model.provider`、`model.protocol`、`model.model_name` 必须为有效的非空字符串。
- `model.protocol` 只能填写 `openai` 或 `anthropic`。
- 配置列表不允许出现空名称或完全相同的重复名称。
- 运行次数、Token 预算等受限制的整数参数必须满足对应范围。
- `memory.enabled`、`memory.files` 必须符合预期类型。

需要注意，当前实现只对模型字典中的部分常用参数执行显式校验，例如 `max_tokens`、`max_completion_tokens`、`max_retries`。其他模型参数仍需由 `LLMClient` 和实际模型服务验证。

配置加载成功并不代表模型地址可连接、API Key 有效、工具已经注册或类路径指向的模块实际存在。

## 9. 开发与使用约定

1. **新增普通 Agent 实例**：创建新的 YAML，调整名称、模型、Prompt、Tool 等配置，通常不需要新增 Python 类。
2. **新增 Agent 实现**：继承 `BaseAgent`，在 `agent_class` 中填写完整导入路径；特殊参数放入 `agent_options`。
3. **新增 Loop 实现**：继承 `BaseAgentLoop`，在 `loop_class` 中填写完整导入路径；特殊参数放入 `loop_options`。
4. **新增模型服务**：如果兼容当前支持的 OpenAI 或 Anthropic 协议，一般只需修改 `provider`、`protocol`、`model_name` 和 `base_url`；不兼容的接口需要扩展 `LLMClient`。
5. **配置安全**：API Key 应保存在环境变量中，YAML 中不存储明文密钥；`agent_class`、`loop_class` 允许动态导入 Python 代码，因此只应加载可信的本地配置。

## 10. 官方参考文档

- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [DeepSeek API 文档](https://api-docs.deepseek.com/zh-cn/)
- [Ollama OpenAI 兼容接口](https://docs.ollama.com/api/openai-compatibility)
- [LM Studio OpenAI 兼容接口](https://lmstudio.ai/docs/developer/openai-compat)
- [vLLM OpenAI 兼容服务](https://docs.vllm.ai/en/latest/serving/openai_compatible_server/)

模型 ID、兼容协议和服务地址可能随服务版本变化，具体应以相应服务的官方文档为准。
