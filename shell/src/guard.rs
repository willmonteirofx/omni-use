//! Safety guard: while the automation drives the mouse, a real hand on it
//! for 1 s pauses the run and gives the mouse back to the user.
//!
//! A low-level mouse hook sees every move. The agent moves the cursor with
//! SendInput, which Windows flags as LLMHF_INJECTED; anything without that
//! flag is the physical mouse. Continuous physical movement (no gap longer
//! than MAX_GAP) lasting HOLD triggers the pause.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter};
use windows_sys::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, GetMessageW, SetWindowsHookExW, LLMHF_INJECTED, MSG, MSLLHOOKSTRUCT,
    WH_MOUSE_LL, WM_MOUSEMOVE,
};

const HOLD: Duration = Duration::from_millis(1000);
const MAX_GAP: Duration = Duration::from_millis(250);

static ARMED: AtomicBool = AtomicBool::new(false);
/// Milliseconds since EPOCH (below) of the first / latest physical move of
/// the current streak; 0 = no streak.
static STREAK_START: AtomicU64 = AtomicU64::new(0);
static LAST_MOVE: AtomicU64 = AtomicU64::new(0);
static EPOCH: OnceLock<Instant> = OnceLock::new();
static APP: OnceLock<AppHandle> = OnceLock::new();

fn now_ms() -> u64 {
    EPOCH.get_or_init(Instant::now).elapsed().as_millis() as u64 + 1
}

/// Arms the guard while a run is driving the mouse, disarms it otherwise.
pub fn set_armed(on: bool) {
    STREAK_START.store(0, Ordering::SeqCst);
    ARMED.store(on, Ordering::SeqCst);
}

unsafe extern "system" fn hook(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 && wparam as u32 == WM_MOUSEMOVE && ARMED.load(Ordering::Relaxed) {
        let info = &*(lparam as *const MSLLHOOKSTRUCT);
        if info.flags & LLMHF_INJECTED == 0 {
            on_physical_move();
        }
    }
    CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam)
}

fn on_physical_move() {
    let now = now_ms();
    let last = LAST_MOVE.swap(now, Ordering::SeqCst);
    let start = STREAK_START.load(Ordering::SeqCst);
    if start == 0 || now - last > MAX_GAP.as_millis() as u64 {
        STREAK_START.store(now, Ordering::SeqCst);
        return;
    }
    if now - start >= HOLD.as_millis() as u64 && ARMED.swap(false, Ordering::SeqCst) {
        // Never block the hook (Windows drops slow hooks): report off-thread.
        std::thread::spawn(|| {
            let _ = ureq::post(format!("http://127.0.0.1:{}/pause", crate::AGENT_PORT))
                .send_json(serde_json::json!({ "reason": "mouse" }));
            if let Some(app) = APP.get() {
                let _ = app.emit("takeover", ());
            }
        });
    }
}

/// Installs the hook on its own thread (a low-level hook needs a message loop).
pub fn install(app: AppHandle) {
    let _ = APP.set(app);
    std::thread::spawn(|| unsafe {
        let hook = SetWindowsHookExW(WH_MOUSE_LL, Some(hook), GetModuleHandleW(std::ptr::null()), 0);
        if hook.is_null() {
            eprintln!("[guard] SetWindowsHookExW failed; the mouse takeover pause is disabled");
            return;
        }
        let mut msg: MSG = std::mem::zeroed();
        while GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) > 0 {}
    });
}
