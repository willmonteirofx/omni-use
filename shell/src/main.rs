// omni-all: computer use on the whole desktop. OmniParser V2 reads the
// screen, a local Qwen (llama.cpp) + OpenJev-style decide() choose the next
// step, SendInput executes it (agent/). This shell is only:
// - "input": a floating, draggable prompt (ui/index.html) - the whole UI;
// - "badge": a click-through spinner that rides next to the cursor while the
//   automation holds the mouse, and shows a ripple on every click;
// - the mouse guard (guard.rs) that pauses the run when the user moves the
//   mouse by hand for 1 s;
// - spawning/killing llama-server, the Python agent and whisper-server
//   (voice input, voice.rs - shared with Omni Use);
// - the settings commands (model/context, llm.rs);
// - "debug": optional click-through overlay drawing OmniParser's boxes over
//   the screen at each step.
// All windows are excluded from screen capture, so the screenshots sent to
// OmniParser show the desktop behind them.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod guard;
mod llm;
mod voice;

use std::sync::atomic::{AtomicBool, AtomicIsize, Ordering};
use std::sync::{Arc, Mutex};

use tauri::{Emitter, Manager, WebviewUrl, WebviewWindowBuilder};
use windows_sys::Win32::Foundation::{HWND, POINT};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    GetCursorPos, GetWindow, GetWindowLongW, GetWindowTextLengthW, IsIconic, IsWindowVisible,
    SetForegroundWindow, SetWindowDisplayAffinity, SetWindowPos, GWL_EXSTYLE, GW_HWNDNEXT,
    HWND_TOPMOST, SWP_NOACTIVATE, SWP_NOSIZE, WDA_EXCLUDEFROMCAPTURE, WS_EX_TOOLWINDOW,
};

pub const AGENT_PORT: u16 = 8766;
/// Side of the (square) badge window, logical px; centered on the cursor.
const BADGE_SIZE: f64 = 120.0;

static BADGE_ON: AtomicBool = AtomicBool::new(false);
static BADGE_HWND: AtomicIsize = AtomicIsize::new(0);

/// The exe ends up in `shell/target/{debug,release}/`: the project root is
/// three levels up.
fn project_root() -> std::path::PathBuf {
    std::env::current_exe()
        .expect("failed to get current exe path")
        .ancestors()
        .nth(4)
        .expect("unexpected exe location")
        .to_path_buf()
}

fn is_healthy(port: u16) -> bool {
    let agent = ureq::Agent::config_builder()
        .timeout_global(Some(std::time::Duration::from_millis(800)))
        .build()
        .new_agent();
    agent.get(format!("http://127.0.0.1:{port}/health")).call().is_ok()
}

/// Spawns a helper process without a console window, its output going to
/// logs/<name>.log (overwritten on each start).
fn spawn_hidden(cmd: &mut std::process::Command, name: &str) -> Option<std::process::Child> {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let dir = project_root().join("logs");
    let _ = std::fs::create_dir_all(&dir);
    if let Ok(log) = std::fs::File::create(dir.join(format!("{name}.log"))) {
        if let Ok(err) = log.try_clone() {
            cmd.stdout(log).stderr(err);
        }
    }
    cmd.creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| eprintln!("[shell] failed to spawn {:?}: {e}", cmd.get_program()))
        .ok()
}

fn spawn_agent() -> Option<std::process::Child> {
    if is_healthy(AGENT_PORT) {
        eprintln!("[shell] an agent is already running on port {AGENT_PORT}, reusing it");
        return None;
    }
    let dir = project_root().join("agent");
    let python = dir.join(".venv").join("Scripts").join("python.exe");
    if !python.exists() {
        eprintln!("[shell] {} not found - run scripts\\install_agent.bat", python.display());
        return None;
    }
    spawn_hidden(std::process::Command::new(python).arg(dir.join("server.py")).current_dir(&dir), "agent")
}

struct Children(Mutex<Vec<std::process::Child>>);

fn hwnd_of(win: &tauri::WebviewWindow) -> HWND {
    win.hwnd().map(|h| h.0 as HWND).unwrap_or(std::ptr::null_mut())
}

/// The run started/stopped holding the mouse: arm the guard, show the badge.
#[tauri::command]
fn set_driving(on: bool, app: tauri::AppHandle) {
    guard::set_armed(on);
    BADGE_ON.store(on, Ordering::SeqCst);
    if let Some(badge) = app.get_webview_window("badge") {
        let _ = if on { badge.show() } else { badge.hide() };
    }
}

/// Shows/hides the debug overlay (OmniParser's boxes drawn over the screen).
#[tauri::command]
fn toggle_debug(app: tauri::AppHandle) -> bool {
    let Some(debug) = app.get_webview_window("debug") else { return false };
    let visible = debug.is_visible().unwrap_or(false);
    let _ = if visible { debug.hide() } else { debug.show() };
    !visible
}

/// The agent clicked: the badge plays a ripple.
#[tauri::command]
fn badge_click(app: tauri::AppHandle) {
    let _ = app.emit_to("badge", "ripple", ());
}

/// After a task is sent the input has the keyboard focus; hand it to the
/// window right below it so the agent's typing goes to the desktop, not to us.
#[tauri::command]
fn release_focus(window: tauri::WebviewWindow) {
    unsafe {
        let own = hwnd_of(&window);
        let badge = BADGE_HWND.load(Ordering::SeqCst) as HWND;
        let mut h = GetWindow(own, GW_HWNDNEXT);
        while !h.is_null() {
            let tool = GetWindowLongW(h, GWL_EXSTYLE) as u32 & WS_EX_TOOLWINDOW != 0;
            if h != badge && IsWindowVisible(h) != 0 && IsIconic(h) == 0 && !tool && GetWindowTextLengthW(h) > 0 {
                SetForegroundWindow(h);
                return;
            }
            h = GetWindow(h, GW_HWNDNEXT);
        }
    }
}

/// Keeps the badge centered on the cursor while it is shown (~120 Hz).
fn follow_cursor(scale: f64) {
    std::thread::spawn(move || {
        let half = (BADGE_SIZE * scale / 2.0) as i32;
        let mut last = (i32::MIN, i32::MIN);
        loop {
            std::thread::sleep(std::time::Duration::from_millis(8));
            if !BADGE_ON.load(Ordering::Relaxed) {
                continue;
            }
            let mut p = POINT { x: 0, y: 0 };
            unsafe { GetCursorPos(&mut p) };
            if (p.x, p.y) == last {
                continue;
            }
            last = (p.x, p.y);
            let hwnd = BADGE_HWND.load(Ordering::Relaxed) as HWND;
            unsafe {
                SetWindowPos(hwnd, HWND_TOPMOST, p.x - half, p.y - half, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE);
            }
        }
    });
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            set_driving,
            badge_click,
            release_focus,
            toggle_debug,
            llm::get_llm_settings,
            llm::apply_llm_settings,
            voice::voice_start,
            voice::voice_stop,
            voice::voice_status,
        ])
        .setup(|app| {
            app.manage(llm::LlmState(Arc::new(Mutex::new(llm::spawn_llm_server(&llm::load_settings())))));
            app.manage(Children(Mutex::new(spawn_agent().into_iter().collect())));

            let input = WebviewWindowBuilder::new(app, "input", WebviewUrl::App("index.html".into()))
                .title("omni-all")
                .inner_size(560.0, 64.0)
                .decorations(false)
                .transparent(true)
                .shadow(false)
                .resizable(false)
                .always_on_top(true)
                .build()?;
            // Start near the bottom center of the primary monitor.
            if let Some(m) = input.primary_monitor()? {
                let s = m.scale_factor();
                let size = m.size().to_logical::<f64>(s);
                let _ = input.set_position(tauri::LogicalPosition::new((size.width - 560.0) / 2.0, size.height - 150.0));
            }

            let badge = WebviewWindowBuilder::new(app, "badge", WebviewUrl::App("badge.html".into()))
                .title("omni-all cursor")
                .inner_size(BADGE_SIZE, BADGE_SIZE)
                .decorations(false)
                .transparent(true)
                .shadow(false)
                .resizable(false)
                .always_on_top(true)
                .skip_taskbar(true)
                .focused(false)
                .visible(false)
                .build()?;
            badge.set_ignore_cursor_events(true)?;
            BADGE_HWND.store(hwnd_of(&badge) as isize, Ordering::SeqCst);
            follow_cursor(badge.scale_factor().unwrap_or(1.0));

            // Debug overlay: transparent, click-through, covers the primary
            // monitor and draws OmniParser's boxes where the elements really
            // are. Excluded from capture like the others, so it never ends up
            // in what OmniParser parses. Hidden until the input's eye button.
            let debug = WebviewWindowBuilder::new(app, "debug", WebviewUrl::App("debug.html".into()))
                .title("omni-all debug")
                .decorations(false)
                .transparent(true)
                .shadow(false)
                .resizable(false)
                .always_on_top(true)
                .skip_taskbar(true)
                .focused(false)
                .visible(false)
                .build()?;
            if let Some(m) = debug.primary_monitor()? {
                debug.set_position(*m.position())?;
                debug.set_size(*m.size())?;
            }
            debug.set_ignore_cursor_events(true)?;

            for w in [&input, &badge, &debug] {
                unsafe { SetWindowDisplayAffinity(hwnd_of(w), WDA_EXCLUDEFROMCAPTURE) };
            }
            guard::install(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if window.label() == "input" {
                    // Closing the input quits: stop any run and the helpers.
                    let _ = ureq::post(format!("http://127.0.0.1:{AGENT_PORT}/stop")).send_empty();
                    let llm = window.state::<llm::LlmState>().0.lock().unwrap().take();
                    for mut c in window.state::<Children>().0.lock().unwrap().drain(..).chain(llm) {
                        let _ = c.kill();
                        let _ = c.wait();
                    }
                    voice::shutdown();
                    window.app_handle().exit(0);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running omni-all");
}
