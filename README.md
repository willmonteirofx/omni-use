# 🖥️ Omni-Use: Local Desktop Computer Use Agent

> **100% Local Autonomous Computer Use Agent for Windows**  
> Intelligent mouse and keyboard automation powered by computer vision, quantized local LLMs/VLMs, and real-time multilingual OCR.

---

## 📌 Overview

**Omni-Use** is an autonomous desktop automation platform (*Computer Use*) that runs **100% locally** on Windows workstations. No screenshots, credentials, or user data are ever uploaded to cloud servers or third-party APIs.

Unlike browser-only automation tools limited to DOM trees, Omni-Use analyzes physical desktop screens through **hybrid computer vision (OmniParser V2)**, detects interactable UI elements and bounding boxes, reasons over decisions with **local language and vision models (Qwen via llama.cpp)**, and drives the operating system natively and safely using **Win32 SendInput**.

```
   ┌────────────────────────────────────────────────────────┐
   │                     Desktop Screen                     │
   └───────────────────────────┬────────────────────────────┘
                               │ (Fast screen capture via mss)
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                    OmniParser V2                       │
   │  - YOLOv8 (Icon & UI Element Detection)                │
   │  - Florence-2 (Semantic Icon Captioning)               │
   │  - EasyOCR / PaddleOCR (PT / EN Text Recognition)      │
   └───────────────────────────┬────────────────────────────┘
                               │ [id] type "text" @ (x, y) + labeled image
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                 Local LLM / VLM (llama.cpp)            │
   │  - Qwen 3.5 / 2.5 (4B / 9B Instruct + Vision mmproj)   │
   │  - Structured JSON Action Proposal                     │
   └───────────────────────────┬────────────────────────────┘
                               │ Proposed action
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │             OpenJev decide() Safety Gate               │
   │  - Logit probability check for destructive actions     │
   │  - Semantic validation of task completion ("done")     │
   └───────────────────────────┬────────────────────────────┘
                               │ Approved action
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │               Win32 Control & Mouse Guard              │
   │  - SendInput with natural curved glide trajectory      │
   │  - Instant pause on human mouse takeover (Low-level)   │
   └────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Features

- 👁️ **Local Computer Vision (OmniParser V2):** Accurately identifies buttons, icons, and input fields across any Windows application without requiring accessibility trees or source code.
- 🧠 **Local LLM/VLM Reasoning:** Native GPU-accelerated execution via `llama-server` (CUDA 12.4), supporting Qwen text and multimodal vision projectors (`mmproj`).
- 🛡️ **Active Safety & Mouse Guard:**
  - **Human Conflict Detection:** Moving the mouse manually for 1 second instantly pauses the agent, yielding control back to the user.
  - **Destructive Action Gate (`decide`):** High-risk actions (e.g., delete, close without saving, send, purchase) require explicit user approval.
- 🪟 **Floating Lightweight UI (Tauri v2):** Minimalist translucent command bar, status indicators, and an animated cursor badge excluded from screen capture (`WDA_EXCLUDEFROMCAPTURE`).
- 🎯 **Target Window Confinement (`OMNI_CONFINE_TITLE`):** Ability to restrict all clicks, typing, and keystrokes exclusively to a specific window during testing.
- 🎙️ **Local Voice Input:** Fast offline speech-to-text integration powered by `whisper.cpp` (`large-v3-turbo`).

---

## 🧩 Project Architecture

```
omni-use/
├── agent/                  # Python Sidecar (Core Agent Engine)
│   ├── core.py             # Main Computer Use loop, Safety Gate & Action execution
│   ├── vision.py           # Screen capture, OCR extraction, and OmniParser parsing
│   ├── control.py          # Mouse & keyboard emulation via Win32 SendInput
│   ├── llm_client.py       # HTTP client for llama.cpp (Chat, Vision & decide)
│   ├── server.py           # Local HTTP server (port 8766) communicating with the Shell
│   └── config.py           # Configuration, ports, and environment variables
├── omniparser/             # Official Microsoft OmniParser submodule
├── shell/                  # Native Rust Desktop Shell (Tauri v2)
│   ├── src/main.rs         # Window management, process lifecycle, and background orchestration
│   ├── src/guard.rs        # Low-level Windows Mouse Hook (detects human intervention)
│   ├── src/llm.rs          # llama-server background process manager
│   └── src/voice.rs        # Audio capture and whisper.cpp streaming
├── ui/                     # Web Frontend (HTML5, CSS3, Vanilla JS)
│   ├── index.html/script.js# Floating prompt bar and action status
│   └── badge.html          # Non-intrusive cursor badge indicator
├── scripts/                # Automated batch scripts for setup, models, and builds
├── requirements.txt        # Python agent dependencies
└── README.md
```

---

## 🤖 Models, Engines & Credits

Omni-Use builds upon state-of-the-art open-source AI models and native runtime engines:

| Component | Role | Creator / Source | Original License |
| :--- | :--- | :--- | :--- |
| **OmniParser V2** | Screen UI parsing & parsing pipeline | [Microsoft Research](https://github.com/microsoft/OmniParser) | MIT |
| **Florence-2** | Semantic icon captioning | [Microsoft](https://huggingface.co/microsoft/Florence-2-base) | MIT |
| **YOLOv8** (Detector) | Bounding box icon detector | [Ultralytics](https://github.com/ultralytics/ultralytics) | AGPL-3.0 / Commercial |
| **Qwen 2.5 / 3.5** | Instruction following, reasoning & VLM | [Alibaba Cloud / Qwen Team](https://github.com/QwenLM/Qwen2.5) | Apache 2.0 / Qwen License |
| **llama.cpp** | High-performance GPU LLM/VLM inference | [Georgi Gerganov & Community](https://github.com/ggml-org/llama.cpp) | MIT |
| **whisper.cpp** | Ultra-fast local voice transcription | [Georgi Gerganov](https://github.com/ggml-org/whisper.cpp) / [OpenAI](https://github.com/openai/whisper) | MIT |
| **EasyOCR** | Optical Character Recognition engine | [JaidedAI](https://github.com/JaidedAI/EasyOCR) | Apache 2.0 |
| **PaddleOCR** | Deep learning OCR framework | [PaddlePaddle / Baidu](https://github.com/PaddlePaddle/PaddleOCR) | Apache 2.0 |
| **Tauri v2** | Lightweight desktop application shell | [Tauri Apps](https://tauri.app/) | MIT / Apache 2.0 |

---

## ⚖️ Licensing & Commercialization Guidelines

The core codebase of **Omni-Use** is released under the **[MIT License](LICENSE)**.

### 💼 Commercial, Cloud & Open-Source Guidelines:

1. **Open-Source & Community Contributions:**
   - The project is fully open for community forks, bug fixes, enhancements, and custom integrations.
2. **Permissive Upstream Engines (MIT / Apache 2.0):**
   - The majority of underlying components (Tauri, llama.cpp, Whisper, Florence-2, EasyOCR, PaddleOCR, Qwen) use highly permissive licenses suitable for commercial products, cloud hosting, and SaaS infrastructure.
3. **Ultralytics YOLO (AGPL-3.0) Notice:**
   - Microsoft OmniParser V2 relies on `ultralytics` for its icon detector. Under the **AGPL-3.0** license, if you host a modified backend service or distribute closed-source binaries over a network, AGPL copyleft terms may apply.
   - **For enterprise commercialization or closed-source cloud backends**, you can:
     - *(Option A)* Keep your agent core open-source (as structured in this repository).
     - *(Option B)* Obtain an Enterprise Commercial License directly from Ultralytics.
     - *(Option C)* Replace the icon detector module with Apache 2.0 / MIT models (e.g., RT-DETR or DETR architectures).

---

## 🛠️ System Requirements

- **Operating System:** Windows 10 or Windows 11 (64-bit).
- **GPU (Recommended):** NVIDIA GPU with **CUDA 12.4+** support and at least **8 GB VRAM** (12 GB+ recommended for running 9B VLMs concurrently with OmniParser).
- **Python:** Version **3.12** available on system `PATH`.
- **Rust & Cargo:** For compiling the Tauri desktop shell ([rustup.rs](https://rustup.rs/)).
- **Visual Studio C++ Build Tools:** C++ CMake and MSVC v143+ tools.

---

## 📦 Step-by-Step Installation

Open a terminal (PowerShell or Command Prompt) in your desired directory:

### 1. Clone the Repository and Submodules
```powershell
git clone --recurse-submodules https://github.com/willmonteirofx/omni-use.git
cd omni-use
```

*(If cloned without submodules, run: `git submodule update --init --recursive`)*

### 2. Install the Python Agent Environment
Creates the virtual environment at `agent/.venv` with PyTorch CUDA 12.4 and all required dependencies:
```cmd
scripts\install_agent.bat
```

### 3. Download OmniParser V2 Model Weights
Downloads the YOLO icon detector and Florence-2 captioner weights into `models\omniparser`:
```cmd
scripts\download_models.bat
```

### 4. Download Language Models (Qwen)
Choose based on your available VRAM:
- **Qwen 3.5 4B (Recommended for 8 GB VRAM GPUs):**
  ```cmd
  scripts\download_qwen4b.bat
  ```
- **Qwen 3.5 9B (Stronger reasoning, for 12 GB+ VRAM GPUs):**
  ```cmd
  scripts\download_qwen9b.bat
  scripts\download_qwen9b_vision.bat
  ```

### 5. Fetch Pre-built CUDA Binaries
```cmd
scripts\fetch_llama_cuda.bat
scripts\fetch_whisper_cuda.bat
scripts\download_whisper_model.bat
```

### 6. Build the Desktop Shell (Tauri)
```cmd
scripts\build_shell.bat
```

---

## 🏃 Usage & Execution

Launch the compiled release executable:

```cmd
shell\target\release\omni-all.exe
```

When started:
1. The floating command bar will appear on your screen.
2. `llama-server` and the Python `agent server` will start automatically in the background.
3. Type your command (e.g., *"Open Notepad, write 'Hello World' and save the file to the Desktop"*) and hit `Enter`.

### ⚙️ Optional Configuration (`settings.json`)

Create a `settings.json` file in the root folder to customize inference parameters:

```json
{
  "model": "qwen3.5-4b-q4_k_m.gguf",
  "ctx": 16384,
  "threads": 8,
  "temperature": 0.2
}
```

---

## 🤝 Contributing

Contributions from the open-source community are highly encouraged! Areas of interest include:
- Native support for new VLM architectures (e.g., Qwen2.5-VL native, MiniCPM-V).
- OCR throughput optimizations and latency reduction in the parsing loop.
- Multi-monitor coordinate scaling and dynamic DPI support.
- Cloud orchestration adapters and multi-agent coordination.

To contribute:
1. Fork the project.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'feat: Add support for amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
5. Open a **Pull Request**.

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more details.
