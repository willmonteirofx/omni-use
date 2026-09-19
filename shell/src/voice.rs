//! Local voice input: records the default mic natively (cpal, so no WebView2
//! mic permission prompt) and transcribes with Whisper large-v3-turbo on the
//! GPU (bin/whisper, CUDA build from scripts/fetch_whisper_cuda.bat).
//!
//! Whisper runs as a long-lived `whisper-server`, started on the first mic
//! click (it loads while the user talks): spawning `whisper-cli` per clip
//! reloaded the 1.6 GB model every time - measured 13 s of a 15 s call when
//! RAM is tight - while the actual GPU transcription takes ~1.5 s.

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;
use std::sync::mpsc;
use std::sync::{Arc, Mutex, OnceLock};
use std::thread::JoinHandle;

use crate::project_root;

const MODEL_FILE: &str = "ggml-large-v3-turbo.bin";
/// Caps memory use if the user forgets to stop recording.
const MAX_SECONDS: usize = 120;
const TARGET_RATE: u32 = 16_000;
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const SERVER_PORT: u16 = 8178;
/// Peak level below which a clip is treated as silence. Whisper otherwise
/// "hears" things in a quiet room (a lone "you" is the classic).
const SILENCE_PEAK: f32 = 0.03;

/// cpal's Stream is !Send, so it lives on its own thread; we only keep the
/// stop channel, the thread handle and the shared sample buffer.
struct Recording {
    stop: mpsc::Sender<()>,
    thread: JoinHandle<()>,
    samples: Arc<Mutex<Vec<f32>>>,
    rate: u32,
    channels: u16,
}

fn state() -> &'static Mutex<Option<Recording>> {
    static STATE: OnceLock<Mutex<Option<Recording>>> = OnceLock::new();
    STATE.get_or_init(|| Mutex::new(None))
}

fn model_path() -> PathBuf {
    project_root().join("models").join(MODEL_FILE)
}

pub fn is_recording() -> bool {
    state().lock().unwrap().is_some()
}

/// Starts capturing the default input device. Returns (sample rate, channels).
pub fn start_recording() -> Result<(u32, u16), String> {
    let mut st = state().lock().unwrap();
    if st.is_some() {
        return Err("already recording".into());
    }
    let samples = Arc::new(Mutex::new(Vec::new()));
    let (stop_tx, stop_rx) = mpsc::channel::<()>();
    let (ready_tx, ready_rx) = mpsc::channel::<Result<(u32, u16), String>>();
    let buf = samples.clone();
    let thread = std::thread::spawn(move || {
        let stream = match open_stream(buf) {
            Ok((s, fmt)) => {
                let _ = ready_tx.send(Ok(fmt));
                s
            }
            Err(e) => {
                let _ = ready_tx.send(Err(e));
                return;
            }
        };
        let _ = stop_rx.recv(); // blocks until stop (or sender dropped)
        drop(stream);
    });
    let (rate, channels) = ready_rx.recv().map_err(|e| e.to_string())??;
    *st = Some(Recording { stop: stop_tx, thread, samples, rate, channels });
    Ok((rate, channels))
}

fn open_stream(buf: Arc<Mutex<Vec<f32>>>) -> Result<(cpal::Stream, (u32, u16)), String> {
    let device = cpal::default_host()
        .default_input_device()
        .ok_or("no microphone found")?;
    let config = device.default_input_config().map_err(|e| e.to_string())?;
    let rate = config.sample_rate();
    let channels = config.channels();
    let cap = rate as usize * channels as usize * MAX_SECONDS;
    let err = |e| eprintln!("[voice] stream error: {e}");
    let stream = match config.sample_format() {
        cpal::SampleFormat::F32 => device.build_input_stream(
            config.into(),
            move |d: &[f32], _: &_| push(&buf, cap, d.iter().copied()),
            err,
            None,
        ),
        cpal::SampleFormat::I16 => device.build_input_stream(
            config.into(),
            move |d: &[i16], _: &_| push(&buf, cap, d.iter().map(|&s| s as f32 / 32768.0)),
            err,
            None,
        ),
        f => return Err(format!("unsupported sample format {f:?}")),
    }
    .map_err(|e| e.to_string())?;
    stream.play().map_err(|e| e.to_string())?;
    Ok((stream, (rate, channels)))
}

fn push(buf: &Mutex<Vec<f32>>, cap: usize, data: impl Iterator<Item = f32>) {
    let mut b = buf.lock().unwrap();
    let room = cap.saturating_sub(b.len());
    b.extend(data.take(room));
}

/// Stops recording; returns interleaved samples plus (rate, channels).
pub fn stop_recording() -> Result<(Vec<f32>, u32, u16), String> {
    let rec = state().lock().unwrap().take().ok_or("not recording")?;
    let _ = rec.stop.send(());
    let _ = rec.thread.join();
    let samples = std::mem::take(&mut *rec.samples.lock().unwrap());
    Ok((samples, rec.rate, rec.channels))
}

/// Mixes to mono and resamples to 16 kHz (linear interpolation is plenty for speech).
pub fn to_16k_mono(samples: &[f32], rate: u32, channels: u16) -> Vec<i16> {
    let ch = channels.max(1) as usize;
    let mono: Vec<f32> = samples.chunks(ch).map(|c| c.iter().sum::<f32>() / c.len() as f32).collect();
    if mono.is_empty() {
        return Vec::new();
    }
    let step = rate as f64 / TARGET_RATE as f64;
    let n = (mono.len() as f64 / step) as usize;
    (0..n)
        .map(|i| {
            let pos = i as f64 * step;
            let j = pos as usize;
            let a = mono[j];
            let b = *mono.get(j + 1).unwrap_or(&a);
            let s = a + (b - a) * (pos - j as f64) as f32;
            (s.clamp(-1.0, 1.0) * 32767.0) as i16
        })
        .collect()
}

/// Minimal 16 kHz mono 16-bit PCM WAV (44-byte header), no extra dep.
pub fn wav_bytes(pcm: &[i16]) -> Vec<u8> {
    let data_len = (pcm.len() * 2) as u32;
    let mut out = Vec::with_capacity(44 + data_len as usize);
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&(36 + data_len).to_le_bytes());
    out.extend_from_slice(b"WAVEfmt ");
    out.extend_from_slice(&16u32.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes()); // PCM
    out.extend_from_slice(&1u16.to_le_bytes()); // mono
    out.extend_from_slice(&TARGET_RATE.to_le_bytes());
    out.extend_from_slice(&(TARGET_RATE * 2).to_le_bytes());
    out.extend_from_slice(&2u16.to_le_bytes());
    out.extend_from_slice(&16u16.to_le_bytes());
    out.extend_from_slice(b"data");
    out.extend_from_slice(&data_len.to_le_bytes());
    for s in pcm {
        out.extend_from_slice(&s.to_le_bytes());
    }
    out
}

fn server() -> &'static Mutex<Option<std::process::Child>> {
    static SERVER: OnceLock<Mutex<Option<std::process::Child>>> = OnceLock::new();
    SERVER.get_or_init(|| Mutex::new(None))
}

/// Starts whisper-server if it isn't running yet (returns immediately; the
/// model finishes loading in the background).
fn ensure_server() -> Result<(), String> {
    let mut srv = server().lock().unwrap();
    if let Some(child) = srv.as_mut() {
        if child.try_wait().map(|s| s.is_none()).unwrap_or(false) {
            return Ok(());
        }
    }
    let root = project_root();
    let child = Command::new(root.join("bin").join("whisper").join("whisper-server.exe"))
        .args(["-m"]).arg(root.join("models").join(MODEL_FILE))
        .args(["-l", "auto", "-nt", "-sns", "--host", "127.0.0.1", "--port", &SERVER_PORT.to_string()])
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| format!("whisper-server failed to start: {e}"))?;
    *srv = Some(child);
    Ok(())
}

/// Kills whisper-server (called when the app window closes).
pub fn shutdown() {
    if let Some(mut child) = server().lock().unwrap().take() {
        let _ = child.kill();
    }
}

/// Sends a WAV to whisper-server, waiting for it to finish loading if needed.
fn transcribe(wav: Vec<u8>) -> Result<String, String> {
    ensure_server()?;
    let boundary = "omni-all-voice-boundary";
    let mut body = Vec::with_capacity(wav.len() + 512);
    let part = |headers: &str| format!("--{boundary}\r\n{headers}\r\n\r\n");
    body.extend_from_slice(part("Content-Disposition: form-data; name=\"file\"; filename=\"clip.wav\"\r\nContent-Type: audio/wav").as_bytes());
    body.extend_from_slice(&wav);
    body.extend_from_slice(b"\r\n");
    body.extend_from_slice(part("Content-Disposition: form-data; name=\"response_format\"").as_bytes());
    body.extend_from_slice(format!("text\r\n--{boundary}--\r\n").as_bytes());

    let url = format!("http://127.0.0.1:{SERVER_PORT}/inference");
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(90);
    loop {
        let sent = ureq::post(&url)
            .header("Content-Type", format!("multipart/form-data; boundary={boundary}"))
            .send(&body[..]);
        match sent {
            Ok(mut resp) => {
                let text = resp.body_mut().read_to_string().map_err(|e| e.to_string())?;
                return Ok(text.lines().map(str::trim).filter(|l| !l.is_empty()).collect::<Vec<_>>().join(" "));
            }
            // Connection refused while the model is still loading.
            Err(_) if std::time::Instant::now() < deadline => std::thread::sleep(std::time::Duration::from_millis(300)),
            Err(e) => return Err(format!("whisper-server: {e}")),
        }
    }
}

/// Stop + resample + transcribe.
pub fn stop_and_transcribe() -> Result<String, String> {
    let (samples, rate, channels) = stop_recording()?;
    let peak = samples.iter().fold(0.0f32, |m, s| m.max(s.abs()));
    let pcm = to_16k_mono(&samples, rate, channels);
    if pcm.len() < TARGET_RATE as usize / 4 || peak < SILENCE_PEAK {
        return Ok(String::new()); // too short or silent: nothing worth transcribing
    }
    transcribe(wav_bytes(&pcm))
}

// ---- Tauri commands (thin wrappers) ----

#[derive(serde::Serialize)]
pub struct VoiceStatus {
    model_ready: bool,
    recording: bool,
}

#[tauri::command]
pub fn voice_start() -> Result<(), String> {
    start_recording()?;
    // Load Whisper while the user is still talking.
    ensure_server()
}

#[tauri::command]
pub async fn voice_stop() -> Result<String, String> {
    // whisper takes seconds; keep it off the async runtime's worker threads.
    tauri::async_runtime::spawn_blocking(stop_and_transcribe)
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn voice_status() -> VoiceStatus {
    VoiceStatus { model_ready: model_path().is_file(), recording: is_recording() }
}
