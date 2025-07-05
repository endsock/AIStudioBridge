# 🚀 AI Studio Automator & History Bridge 🌉

## 🌟 项目描述
这是一个强大的工具集，旨在通过自动化脚本、智能历史记录管理和兼容 [`OpenAI`](OpenAI) API 的本地服务器，极大地提升您的工作效率和开发体验！它允许您无缝地与本地服务交互，管理历史记录，并模拟 [`OpenAI`](OpenAI) 接口，为您的项目提供更大的灵活性。

## ✨ 主要功能
- **自动化脚本 (`automator.js`)**: 🤖 简化重复任务，提高工作流效率。
- **历史记录伪造 (`historyforger.js`)**: 📜 灵活管理和修改历史记录，用于测试或数据准备。
- **本地历史服务器 (`local_history_server.py`)**: 💾 提供一个本地 API 端点，用于存储和检索历史数据，支持流式传输。
- **[`OpenAI`](OpenAI) 兼容服务器 (`openai_compatible_server.py`)**: 🔌 将本地服务封装为 [`OpenAI`](OpenAI) API 格式，方便与现有工具集成。

## 🛠️ 安装指南

### 前提条件
在开始之前，请确保您的系统已安装以下软件：
- [`Node.js`](Node.js) (推荐 [`v14`](v14) 或更高版本) 🟢: 用于运行 [`JavaScript`](JavaScript) 脚本。
- [`Python`](Python) (推荐 [`v3.8`](v3.8) 或更高版本) 🐍: 用于运行后端服务器。

### 🚀 快速设置
1. **克隆仓库**:
   ```bash
   git clone https://github.com/your-username/AIStudioAutomator.git # 替换为您的实际仓库URL
   cd AIStudioAutomator
   ```
2. **安装 [`Node.js`](Node.js) 依赖**:
   如果您的 [`JavaScript`](JavaScript) 脚本有 [`npm`](npm) 依赖，请运行：
   ```bash
   npm install
   ```
3. **安装 [`Python`](Python) 依赖**:
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
在服务器运行后，您可以执行 [`Node.js`](Node.js) 脚本来利用这些服务。

- **运行自动化工具**:
  ```bash
  node TampermonkeyScript/automator.js
  ```
  此脚本将执行预定义的自动化任务。

- **运行历史伪造工具**:
  ```bash
  node TampermonkeyScript/historyforger.js
  ```
  此脚本用于向本地历史服务器注入或修改历史数据。

## 📂 项目结构
```
.
├── automator.js                # 🤖 主要自动化脚本
├── historyforger.js            # 📜 历史记录伪造脚本
├── local_history_server.py     # 💾 本地历史记录管理服务器 (Python Flask)
├── openai_compatible_server.py # 🔌 OpenAI API 兼容代理服务器 (Python Flask)
├── README.md                   # 📝 项目说明文件 (您正在阅读的这个!)
└── requirements.txt            # 📦 Python 依赖列表
```

## 🤝 贡献
我们非常欢迎您的贡献！如果您想为本项目添砖加瓦，请遵循以下步骤：
1. **Fork** 本仓库。
2. 创建一个新的功能分支 (`git checkout -b feature/your-awesome-feature`)。
3. 提交您的更改 (`git commit -m 'feat: Add amazing feature'`)。
4. 推送到您的分支 (`git push origin feature/your-awesome-feature`)。
5. 创建一个 **Pull Request** ✨，我们会尽快审查！

## 📄 许可证
本项目采用 [`MIT`](MIT) 许可证。详情请参阅 [`LICENSE`](LICENSE) 文件。