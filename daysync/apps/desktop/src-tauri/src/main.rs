#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    net::{SocketAddr, TcpStream},
    path::PathBuf,
    process::Command,
    time::Duration,
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[tauri::command]
fn ensure_dev_api() -> Result<bool, String> {
    if api_is_ready() {
        return Ok(false);
    }

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
        .canonicalize()
        .map_err(|error| format!("Failed to resolve workspace root: {error}"))?;

    let mut command = Command::new("uv");
    command
        .args([
            "run",
            "uvicorn",
            "services.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "17831",
        ])
        .current_dir(repo_root);

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command
        .spawn()
        .map(|_| true)
        .map_err(|error| format!("Failed to start local API: {error}"))
}

fn api_is_ready() -> bool {
    let address: SocketAddr = "127.0.0.1:17831".parse().expect("valid loopback address");
    TcpStream::connect_timeout(&address, Duration::from_millis(250)).is_ok()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![ensure_dev_api])
        .run(tauri::generate_context!())
        .expect("failed to run DaySync desktop");
}
