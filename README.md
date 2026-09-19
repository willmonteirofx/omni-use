# 🖥️ Omni-Use (Local Desktop Computer Use)

> **Agente Autônomo de Computer Use 100% Local para Windows**  
> Controle inteligente do mouse e teclado através de visão computacional, LLMs locais com quantização e OCR multilíngue em tempo real.

---

## 📌 Visão Geral

O **Omni-Use** é uma plataforma de automação e controle autônomo do ambiente Windows (*Computer Use*) que roda **100% localmente** na máquina do usuário, sem necessidade de enviar dados, capturas de tela ou credenciais para servidores de terceiros.

Diferente de automações baseadas apenas em DOM de navegadores, o Omni-Use analisa a tela física por meio de **visão computacional híbrida (OmniParser V2)**, identifica caixas delimitadoras e elementos interativos, processa a decisão por meio de **modelos locais de linguagem e visão (Qwen via llama.cpp)** e interage de forma segura e fluida via **Win32 SendInput**.

```
   ┌────────────────────────────────────────────────────────┐
   │                     Desktop Screen                     │
   └───────────────────────────┬────────────────────────────┘
                               │ (mss captura rápida)
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                    OmniParser V2                       │
   │  - YOLOv8 (Detecção de Ícones & Elementos)             │
   │  - Florence-2 (Captioning Semântico de Ícones)         │
   │  - EasyOCR / PaddleOCR (Extração de Textos PT/EN)      │
   └───────────────────────────┬────────────────────────────┘
                               │ [id] tipo "texto" @ (x, y) + imagem anotada
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                 LLM / VLM Local (llama.cpp)            │
   │  - Qwen 3.5 / 2.5 (4B / 9B Instruct + Vision mmproj)   │
   │  - Geração de Ação estruturada em JSON                 │
   └───────────────────────────┬────────────────────────────┘
                               │ Proposta de ação
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │             OpenJev decide() Safety Gate               │
   │  - Verificação probabilística de ações destrutivas     │
   │  - Validação de término da tarefa ("done")             │
   └───────────────────────────┬────────────────────────────┘
                               │ Ação aprovada
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │               Win32 Control & Mouse Guard              │
   │  - SendInput com curvas de interpolação natural        │
   │  - Interrupção imediata por movimento manual (Guard)   │
   └────────────────────────────────────────────────────────┘
```

---

## 🚀 Principais Funcionalidades

- 👁️ **Visão Computacional Local (OmniParser V2):** Detecta elementos clicáveis, botões, campos de texto e ícones sem depender de acessibilidade ou código-fonte da aplicação alvo.
- 🧠 **Raciocínio com LLMs Locais:** Integração nativa com `llama-server` (CUDA 12.4), suportando modelos Qwen com e sem projetor de visão (`mmproj`).
- 🛡️ **Segurança Ativa & Mouse Guard:**
  - **Detecção de Conflito:** Se o usuário mexer o mouse manualmente por 1 segundo, o agente pausa automaticamente, cedendo o controle.
  - **Safety Gate (`decide`):** Ações com potencial destrutivo (apagar, enviar, comprar, fechar sem salvar) são pausadas e aguardam aprovação explícita.
- 🪟 **Interface Minimalista e Flutuante (Tauri v2):** Barra flutuante translúcida com entrada de comando, controle de pausa/retomada e badge animado no cursor.
- 🎯 **Modo de Confinamento (`OMNI_CONFINE_TITLE`):** Possibilidade de restringir cliques e digitações exclusivamente a uma janela específica durante testes e integrações.
- 🎙️ **Comando de Voz Integrado:** Suporte a transcrição local por voz via `whisper.cpp` (`large-v3-turbo`).

---

## 🧩 Arquitetura do Projeto

```
omni-use/
├── agent/                  # Sidecar Python (Agente Core)
│   ├── core.py             # Loop principal de Computer Use, Safety Gate & Execução
│   ├── vision.py           # Captura de tela, parsing de coordenadas e OCR
│   ├── control.py          # Emulação de mouse/teclado via Win32 SendInput
│   ├── llm_client.py       # Cliente HTTP para o llama.cpp (Chat, Vision & decide)
│   ├── server.py           # Servidor HTTP local (porta 8766) para comunicação com a Shell
│   └── config.py           # Constantes, portas e variáveis de ambiente
├── omniparser/             # Submódulo oficial Microsoft OmniParser
├── shell/                  # Shell Desktop nativo em Rust (Tauri v2)
│   ├── src/main.rs         # Gerenciador de janelas, ciclo de vida e subprocessos
│   ├── src/guard.rs        # Low-level Windows Mouse Hook (detecção de controle humano)
│   ├── src/llm.rs          # Gerenciamento do ciclo de vida do llama-server
│   └── src/voice.rs        # Integração de áudio e streaming do whisper.cpp
├── ui/                     # Interface gráfica do usuário (HTML5, CSS3, Vanilla JS)
│   ├── index.html/script.js# Barra flutuante de comandos e status
│   └── badge.html          # Indicador visual próximo ao cursor durante execução
├── scripts/                # Automação de setup, download de modelos e compilação
├── requirements.txt        # Dependências Python do agente
└── README.md
```

---

## 🤖 Modelos e Engines Utilizados & Créditos

O Omni-Use integra diversas tecnologias de ponta do ecossistema Open Source e de Inteligência Artificial:

| Componente | Função | Criador / Repositório | Licença Original |
| :--- | :--- | :--- | :--- |
| **OmniParser V2** | Parser de UI de tela | [Microsoft Research](https://github.com/microsoft/OmniParser) | MIT |
| **Florence-2** | Captioning e descrição de ícones | [Microsoft](https://huggingface.co/microsoft/Florence-2-base) | MIT |
| **YOLOv8** (Detector) | Detecção de caixas delimitadoras | [Ultralytics](https://github.com/ultralytics/ultralytics) | AGPL-3.0 / Commercial |
| **Qwen 2.5 / 3.5** | Raciocínio, tomada de decisão e VLM | [Alibaba Cloud / Qwen Team](https://github.com/QwenLM/Qwen2.5) | Apache 2.0 / Qwen License |
| **llama.cpp** | Inferência LLM/VLM acelerada por GPU | [Georgi Gerganov & Comunidade](https://github.com/ggml-org/llama.cpp) | MIT |
| **whisper.cpp** | Reconhecimento de fala local ultrarrápido | [Georgi Gerganov](https://github.com/ggml-org/whisper.cpp) / [OpenAI](https://github.com/openai/whisper) | MIT |
| **EasyOCR** | Reconhecimento Óptico de Caracteres | [JaidedAI](https://github.com/JaidedAI/EasyOCR) | Apache 2.0 |
| **PaddleOCR** | Motor OCR e Deep Learning | [PaddlePaddle / Baidu](https://github.com/PaddlePaddle/PaddleOCR) | Apache 2.0 |
| **Tauri v2** | Framework para aplicação Desktop leve | [Tauri Apps](https://tauri.app/) | MIT / Apache 2.0 |

---

## ⚖️ Licenciamento & Diretrizes Comerciais

O código-fonte do **Omni-Use** está licenciado sob a licença **[MIT](LICENSE)**.

### 💼 Considerações para Monetização, Nuvem e Serviços Proprietários:

1. **Uso Aberto e Contribuições da Comunidade:**
   - O projeto é 100% aberto para a comunidade clonar, estudar, corrigir bugs e submeter Pull Requests.
2. **Engines Permissivas (MIT / Apache 2.0):**
   - A vasta maioria dos componentes (Tauri, llama.cpp, Whisper, Florence-2, EasyOCR, PaddleOCR, Qwen) possui licenças extremamente permissivas que permitem uso comercial, distribuição e hospedagem em nuvem.
3. **Atenção ao Componente YOLO (Ultralytics AGPL-3.0):**
   - O OmniParser V2 utiliza internamente modelos treinados com o framework `ultralytics`. Sob a licença **AGPL-3.0**, caso você ofereça o serviço via rede/SaaS ou faça distribuições fechadas com modificações sem disponibilizar o código-fonte, aplicam-se os termos da AGPL-3.0.
   - **Para monetização e SaaS comercial em larga escala**, você pode:
     - *(Opção A)* Manter o core do agente sob licença aberta (como este repositório).
     - *(Opção B)* Adquirir a Licença Comercial Enterprise junto à Ultralytics.
     - *(Opção C)* Substituir o detector de ícones por arquiteturas sob Apache 2.0/MIT (como RT-DETR, DETR ou YOLOv10/YOLOv11 com pesos independentes).

---

## 🛠️ Requisitos de Sistema

- **Sistema Operacional:** Windows 10 ou Windows 11 (64-bit).
- **GPU (Recomendado):** Placa de vídeo NVIDIA com suporte a **CUDA 12.4+** e no mínimo **8 GB de VRAM** (12 GB+ para execução simultânea do VLM de 9B e OmniParser).
- **Python:** Versão **3.12** instalada e configurada no `PATH`.
- **Rust & Cargo:** Para compilação da Shell Tauri ([rustup.rs](https://rustup.rs/)).
- **Visual Studio C++ Build Tools:** C++ CMake e MSVC v143+.

---

## 📦 Guia de Instalação

Abra um terminal (PowerShell ou Command Prompt) na raiz do projeto:

### 1. Clonar o Repositório e Submódulos
```powershell
git clone --recurse-submodules https://github.com/willmonteirofx/omni-use.git
cd omni-use
```

*(Se já clonou sem o flag de submódulo, execute `git submodule update --init --recursive`)*

### 2. Instalar o Ambiente do Agente (Python)
Cria o ambiente virtual `agent/.venv` com PyTorch CUDA 12.4 e todas as dependências:
```cmd
scripts\install_agent.bat
```

### 3. Baixar os Pesos do OmniParser V2
Baixa os pesos do detector YOLO e do captioner Florence-2:
```cmd
scripts\download_models.bat
```

### 4. Baixar os Modelos de Linguagem (Qwen)
Escolha o modelo de acordo com a capacidade da sua GPU:
- **Qwen 3.5 4B (Recomendado para GPUs com 8 GB VRAM):**
  ```cmd
  scripts\download_qwen4b.bat
  ```
- **Qwen 3.5 9B (Melhor raciocínio, para GPUs com 12 GB+ VRAM):**
  ```cmd
  scripts\download_qwen9b.bat
  scripts\download_qwen9b_vision.bat
  ```

### 5. Baixar as Engines Binárias Pré-compiladas
```cmd
scripts\fetch_llama_cuda.bat
scripts\fetch_whisper_cuda.bat
scripts\download_whisper_model.bat
```

### 6. Compilar a Shell (Tauri Desktop)
```cmd
scripts\build_shell.bat
```

---

## 🏃 Como Executar

Após o build, inicie o executável gerado:

```cmd
shell\target\release\omni-all.exe
```

Ao iniciar:
1. A barra de comando flutuante surgirá no topo da tela.
2. O `llama-server` e o `agent server` serão inicializados automaticamente em segundo plano.
3. Digite sua instrução (ex: *"Abra o bloco de notas, digite 'Olá Mundo' e salve o arquivo na área de trabalho"*) e pressione `Enter`.

### ⚙️ Configurações Opcionais (`settings.json`)

Você pode criar um arquivo `settings.json` na raiz para customizar os parâmetros:

```json
{
  "model": "qwen3.5-4b-q4_k_m.gguf",
  "ctx": 16384,
  "threads": 8,
  "temperature": 0.2
}
```

---

## 🤝 Contribuições

Contribuições são muito bem-vindas! Se você tem ideias para:
- Suporte a novos modelos VLM (ex: Qwen2.5-VL nativo, MiniCPM, Llama-Vision).
- Otimização do pipeline de OCR e redução de latência no OmniParser.
- Integrações em nuvem e orquestração de múltiplos agentes.
- Suporte a múltiplos monitores e melhorias de usabilidade na UI.

Sinta-se à vontade para:
1. Fazer um Fork do projeto.
2. Criar uma branch para sua funcionalidade (`git checkout -b feature/minha-melhoria`).
3. Fazer o commit das suas alterações (`git commit -m 'feat: Adiciona suporte a XYZ'`).
4. Fazer o push da branch (`git push origin feature/minha-melhoria`).
5. Abrir um **Pull Request**.

---

## 📄 Licença

Distribuído sob a licença MIT. Consulte o arquivo [LICENSE](LICENSE) para obter mais informações.
