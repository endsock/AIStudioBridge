# 🚀 AI Studio Automator & History Bridge 🌉

## 🌟 项目描述
这是一个强大的工具集，旨在通过自动化脚本、智能历史记录管理和兼容 [`OpenAI`](OpenAI) API 的本地服务器，极大地提升您的工作效率和开发体验！它允许您无缝地与本地服务交互，管理历史记录，并模拟 [`OpenAI`](OpenAI) 接口，为您的项目提供更大的灵活性。

## ✨ 主要功能
- **自动化脚本 (`TampermonkeyScript/automator.js`)**: 🤖 作为一个油猴脚本，它在浏览器中运行，简化重复任务，提高工作流效率。
- **历史记录伪造 (`TampermonkeyScript/historyforger.js`)**: 📜 作为一个油猴脚本，它在浏览器中运行，灵活管理和修改历史记录，用于测试或数据准备。
- **本地历史服务器 (`local_history_server.py`)**: 💾 提供一个本地 API 端点，用于存储和检索历史数据，支持流式传输。
- **[`OpenAI`](OpenAI) 兼容服务器 (`openai_compatible_server.py`)**: 🔌 将本地服务封装为 [`OpenAI`](OpenAI) API 格式，方便与现有工具集成。

### 👑 核心亮点：完整的函数调用支持！
我们项目最强大的功能是**完全自动化、端到端的函数调用（Function Calling / Tool Calling）**。这意味着您可以：
- **定义您的工具**: 在发送给 API 的请求中定义您的函数（工具）。
- **AI 自动调用**: AI Studio 会智能地决定何时、如何调用您提供的工具，并返回一个符合 OpenAI 格式的 `tool_calls` 响应。
- **并行调用支持**: 系统能够处理 AI 一次请求调用**多个函数**的复杂场景。
- **全周期自动化**: 您可以在客户端执行函数，将结果通过 `role: "tool"` 消息发回，我们的系统会自动将结果提交给 AI Studio，并流式返回 AI 的最终文本回答，完成整个交互闭环。

我们为此功能提供了一个专门的测试脚本，您可以参考 [`test_full_tool_call_cycle.py`](test_full_tool_call_cycle.py) 来了解如何构造请求并测试完整的函数调用周期。

## 🛠️ 安装指南

### 前提条件
在开始之前，请确保您的系统已安装以下软件：
- 浏览器及油猴脚本管理器 (例如 [`Tampermonkey`](Tampermonkey) 或 [`Greasemonkey`](Greasemonkey)) 🌐: 用于运行浏览器端的 [`JavaScript`](JavaScript) 脚本。
- [`Python`](Python) (推荐 [`v3.8`](v3.8) 或更高版本) 🐍: 用于运行后端服务器。

### 🚀 快速设置
1. **克隆仓库**:
   ```bash
   git clone https://github.com/Lianues/AIStudioBridge
   cd AIStudioBridge
   ```
2. **安装 [`Python`](Python) 依赖**:
   我们已为您准备了 [`requirements.txt`](requirements.txt) 文件。请运行：
   ```bash
   pip install -r requirements.txt
   ```

## 🏃‍♂️ 如何使用

### 启动服务器 🖥️
为了使所有功能正常运行，您需要先启动 [`Python`](Python) 服务器。

1. **启动本地历史服务器**:
   ```bash
   python local_history_server.py
   ```
   这将启动一个在 `http://127.0.0.1:5101` 监听的服务器，用于处理历史记录和流式数据。

2. **启动 [`OpenAI`](OpenAI) 兼容服务器**:
   ```bash
   python openai_compatible_server.py
   ```
   此服务器将作为 [`OpenAI`](OpenAI) API 的代理，监听 `http://127.0.0.1:5100`。它会将 [`OpenAI`](OpenAI) 请求转发到本地历史服务器，并以 [`OpenAI`](OpenAI) 兼容的格式返回响应。

### 运行自动化脚本 ⚙️
在服务器运行后，您可以通过安装油猴脚本来利用这些服务。

- **安装油猴脚本**:
  1. 确保您的浏览器已安装 [`Tampermonkey`](Tampermonkey) 或 [`Greasemonkey`](Greasemonkey) 等脚本管理器。
  2. 打开 `TampermonkeyScript/automator.js` 和 `TampermonkeyScript/historyforger.js` 文件，脚本管理器会自动提示您安装。
  3. 安装后，这些脚本将在特定网页加载时自动运行，与您的本地服务器进行交互。

### 打开一个AI Studio Chat历史对话页面,确保不是空对话页面
