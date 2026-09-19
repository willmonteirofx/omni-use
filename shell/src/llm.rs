//! Local LLM (llama-server) process and its user settings.

use std::sync::{Arc, Mutex};

use crate::{is_healthy, project_root, spawn_hidden};

/// Port llama-server listens on (matches agent/config.py's LLM_BASE_URL).
pub const LLM_PORT: u16 = 8081;
const DEFAULT_MODEL_FILE: &str = "qwen3.5-9b-q4_k_m.gguf";
const DEFAULT_CTX: u32 = 16384;

/// Which model llama-server loads and its context. Optional
/// `<project root>/settings.json`, e.g. {"model": "qwen3.5-4b-q4_k_m.gguf", "ctx": 16384}.
#[derive(serde::Serialize, serde::Deserialize, Clone)]
pub struct LlmSettings {
    pub model: String,
    pub ctx: u32,
}

fn settings_path() -> std::path::PathBuf {
    project_root().join("settings.json")
}

/// `*.gguf` files in `models/` starting with `prefix` (half-finished
/// downloads are `.gguf.part`).
fn list_files(prefix: &str) -> Vec<String> {
    let mut files: Vec<String> = std::fs::read_dir(project_root().join("models"))
        .into_iter()
        .flatten()
        .flatten()
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|name| name.starts_with(prefix) && name.ends_with(".gguf"))
        .collect();
    files.sort();
    files
}

/// The vision projector for a model, if downloaded: mmproj-<family>-*.gguf,
/// e.g. qwen3.5-9b-q4_k_m.gguf -> mmproj-qwen3.5-9b-f16.gguf.
fn mmproj_for(model: &str) -> Option<String> {
    let family = model.split("-q").next().unwrap_or(model);
    list_files(&format!("mmproj-{family}-")).into_iter().next()
}

/// The language models (vision projectors excluded).
fn list_models() -> Vec<String> {
    list_files("").into_iter().filter(|f| !f.starts_with("mmproj-")).collect()
}

pub fn load_settings() -> LlmSettings {
    let saved: Option<LlmSettings> = std::fs::read_to_string(settings_path())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok());
    let models = list_models();
    match saved {
        Some(s) if models.contains(&s.model) => s,
        saved => LlmSettings {
            model: if models.iter().any(|m| m == DEFAULT_MODEL_FILE) {
                DEFAULT_MODEL_FILE.to_string()
            } else {
                models.first().cloned().unwrap_or_else(|| DEFAULT_MODEL_FILE.to_string())
            },
            ctx: saved.map(|s| s.ctx).unwrap_or(DEFAULT_CTX),
        },
    }
}

pub fn spawn_llm_server(settings: &LlmSettings) -> Option<std::process::Child> {
    if is_healthy(LLM_PORT) {
        eprintln!("[shell] an LLM server is already running on port {LLM_PORT}, reusing it");
        return None;
    }
    let root = project_root();
    let exe = root.join("bin").join("llama").join("llama-server.exe");
    let model = root.join("models").join(&settings.model);
    if !exe.exists() || !model.exists() {
        eprintln!("[shell] LLM not found (expected {} and {})", exe.display(), model.display());
        return None;
    }
    let mut cmd = std::process::Command::new(&exe);
    cmd.arg("-m")
        .arg(&model)
        .args(["-c", &settings.ctx.to_string(), "-np", "1", "-ngl", "99"])
        .args(["--host", "127.0.0.1", "--port", &LLM_PORT.to_string()]);
    // Vision: scripts\download_qwen9b_vision.bat puts the projector next to
    // the model as mmproj-<model family>-*.gguf, e.g. mmproj-qwen3.5-9b-f16.gguf.
    if let Some(mmproj) = mmproj_for(&settings.model) {
        cmd.arg("--mmproj").arg(root.join("models").join(mmproj));
    }
    spawn_hidden(&mut cmd, "llama")
}


pub struct LlmState(pub Arc<Mutex<Option<std::process::Child>>>);

#[derive(serde::Serialize)]
pub struct LlmSettingsView {
    models: Vec<String>,
    model: String,
    ctx: u32,
    vision: bool,
}

#[tauri::command]
pub fn get_llm_settings() -> LlmSettingsView {
    let s = load_settings();
    let vision = mmproj_for(&s.model).is_some();
    LlmSettingsView { models: list_models(), model: s.model, ctx: s.ctx, vision }
}

/// Saves the settings and restarts llama-server with them. The UI then
/// waits for /health again until the new model has loaded.
#[tauri::command]
pub async fn apply_llm_settings(ctx: u32, model: String, state: tauri::State<'_, LlmState>) -> Result<(), String> {
    if !list_models().contains(&model) {
        return Err(format!("modelo não encontrado: {model}"));
    }
    let settings = LlmSettings { model, ctx: ctx.clamp(2048, 262144) };
    std::fs::write(settings_path(), serde_json::to_string_pretty(&settings).unwrap())
        .map_err(|e| e.to_string())?;
    let mut child = state.0.lock().unwrap();
    if let Some(mut old) = child.take() {
        let _ = old.kill();
        let _ = old.wait(); // frees the port before the new one binds it
    }
    *child = spawn_llm_server(&settings);
    Ok(())
}
