#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Deserialize;
use std::{
    env,
    ffi::OsString,
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::Command,
    thread,
    time::Duration,
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

const API_HOST: &str = "127.0.0.1";
const API_PORT: &str = "17831";
const API_PORT_NUMBER: u16 = 17831;
const WORKSPACE_ENV_KEY: &str = "DAYSYNC_WORKSPACE_ROOT";
const RUNTIME_DIR_NAME: &str = "daysync_runtime";

#[derive(Debug, Clone, PartialEq, Eq)]
struct LaunchPlan {
    program: PathBuf,
    args: Vec<OsString>,
    workspace_root: PathBuf,
    pythonpath: Option<OsString>,
}

#[derive(Debug, Deserialize)]
struct HealthResponse {
    ffmpeg: HealthFfmpeg,
}

#[derive(Debug, Deserialize)]
struct HealthFfmpeg {
    root_path: String,
}

#[tauri::command]
fn ensure_dev_api() -> Result<bool, String> {
    let current_exe = env::current_exe().map_err(|error| format!("Failed to resolve current executable: {error}"))?;
    let workspace_root = resolve_workspace_root(&current_exe)?;

    if api_is_ready() {
        if let Some(health) = fetch_api_health() {
            if api_matches_workspace(&health, &workspace_root) {
                return Ok(false);
            }
            stop_stale_api()?;
        } else {
            stop_stale_api()?;
        }
    }

    let launch_plan = build_launch_plan(&workspace_root);
    let mut command = Command::new(&launch_plan.program);
    command
        .args(&launch_plan.args)
        .current_dir(&launch_plan.workspace_root)
        .env(WORKSPACE_ENV_KEY, &launch_plan.workspace_root);

    if let Some(pythonpath) = launch_plan.pythonpath {
        command.env("PYTHONPATH", pythonpath);
    }

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command
        .spawn()
        .map(|_| true)
        .map_err(|error| format!("Failed to start local API: {error}"))
}

fn api_is_ready() -> bool {
    let address: SocketAddr = format!("{API_HOST}:{API_PORT}")
        .parse()
        .expect("valid loopback address");
    TcpStream::connect_timeout(&address, Duration::from_millis(250)).is_ok()
}

fn fetch_api_health() -> Option<HealthResponse> {
    let body = http_request("GET", "/api/health", None).ok()?;
    serde_json::from_str::<HealthResponse>(&body).ok()
}

fn request_api_shutdown() -> Result<(), String> {
    let _ = http_request("POST", "/api/admin/shutdown", Some("{}"))?;
    Ok(())
}

fn http_request(method: &str, path: &str, body: Option<&str>) -> Result<String, String> {
    let mut stream = TcpStream::connect((API_HOST, API_PORT_NUMBER))
        .map_err(|error| format!("Failed to connect to local API: {error}"))?;
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|error| format!("Failed to set read timeout: {error}"))?;
    let payload = body.unwrap_or("");
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: {API_HOST}:{API_PORT}\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{}",
        payload.len(),
        payload
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| format!("Failed to write request: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("Failed to read response: {error}"))?;

    let mut sections = response.splitn(2, "\r\n\r\n");
    let header = sections.next().unwrap_or_default();
    let body = sections.next().unwrap_or_default().to_string();
    if !header.contains(" 200 ") {
      return Err(format!("Local API request failed: {header}"));
    }
    Ok(body)
}

fn api_matches_workspace(health: &HealthResponse, workspace_root: &Path) -> bool {
    let expected = normalize_path_like(workspace_root.join("tools").join("ffmpeg").join("windows-x64"));
    let actual = normalize_path_like(&health.ffmpeg.root_path);
    actual == expected
}

fn normalize_path_like(path: impl AsRef<Path>) -> String {
    let mut value = path.as_ref().display().to_string();
    if let Some(stripped) = value.strip_prefix("\\\\?\\") {
        value = stripped.to_string();
    }
    value.replace('/', "\\").to_lowercase()
}

fn stop_stale_api() -> Result<(), String> {
    if request_api_shutdown().is_ok() {
        wait_for_api_stop();
        if !api_is_ready() {
            return Ok(());
        }
    }

    #[cfg(windows)]
    {
        kill_api_process_on_windows()?;
        wait_for_api_stop();
        if !api_is_ready() {
            return Ok(());
        }
    }

    Err("Existing local API process is incompatible and could not be stopped.".to_string())
}

fn wait_for_api_stop() {
    for _ in 0..20 {
        if !api_is_ready() {
            return;
        }
        thread::sleep(Duration::from_millis(200));
    }
}

#[cfg(windows)]
fn kill_api_process_on_windows() -> Result<(), String> {
    let output = Command::new("netstat")
        .args(["-ano", "-p", "tcp"])
        .output()
        .map_err(|error| format!("Failed to inspect TCP listeners: {error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let needle = format!("{API_HOST}:{API_PORT}");

    for line in stdout.lines() {
        if !line.contains(&needle) || !line.contains("LISTENING") {
            continue;
        }
        let columns: Vec<&str> = line.split_whitespace().collect();
        if let Some(pid) = columns.last() {
            let status = Command::new("taskkill")
                .args(["/PID", pid, "/F"])
                .status()
                .map_err(|error| format!("Failed to kill stale API process: {error}"))?;
            if status.success() {
                return Ok(());
            }
        }
    }

    Err("Failed to locate stale API process on port 17831.".to_string())
}

fn resolve_workspace_root(current_exe: &Path) -> Result<PathBuf, String> {
    if let Ok(value) = env::var(WORKSPACE_ENV_KEY) {
        let candidate = PathBuf::from(value);
        if is_workspace_root(&candidate) {
            return Ok(candidate);
        }
    }

    let manifest_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let compile_time_root = manifest_root.join("..").join("..").join("..");
    for candidate in workspace_root_candidates(current_exe, Some(&compile_time_root)) {
        if is_workspace_root(&candidate) {
            return candidate
                .canonicalize()
                .map_err(|error| format!("Failed to canonicalize workspace root '{}': {error}", candidate.display()));
        }
    }

    Err(format!(
        "Failed to locate DaySync workspace root from executable '{}'",
        current_exe.display()
    ))
}

fn workspace_root_candidates(current_exe: &Path, compile_time_root: Option<&Path>) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(exe_dir) = current_exe.parent() {
        candidates.push(exe_dir.join(RUNTIME_DIR_NAME));
        candidates.push(exe_dir.join("resources").join(RUNTIME_DIR_NAME));
        candidates.push(exe_dir.to_path_buf());
        for ancestor in exe_dir.ancestors() {
            candidates.push(ancestor.to_path_buf());
            candidates.push(ancestor.join(RUNTIME_DIR_NAME));
        }
    }
    if let Some(root) = compile_time_root {
        candidates.push(root.to_path_buf());
    }
    dedupe_paths(candidates)
}

fn dedupe_paths(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut unique = Vec::new();
    for path in paths {
        if !unique.iter().any(|existing: &PathBuf| existing == &path) {
            unique.push(path);
        }
    }
    unique
}

fn is_workspace_root(candidate: &Path) -> bool {
    candidate.join("pyproject.toml").exists()
        && candidate.join("services").join("api").join("main.py").exists()
        && candidate
            .join("packages")
            .join("daysync_core")
            .join("src")
            .join("daysync_core")
            .exists()
}

fn build_launch_plan(workspace_root: &Path) -> LaunchPlan {
    let bundled_python = workspace_root.join(".venv").join("Scripts").join("python.exe");
    if bundled_python.exists() {
        return LaunchPlan {
            program: bundled_python,
            args: base_python_args(),
            workspace_root: workspace_root.to_path_buf(),
            pythonpath: Some(build_pythonpath(workspace_root)),
        };
    }

    if let Some(program) = command_from_path("uv") {
        return LaunchPlan {
            program,
            args: vec![
                OsString::from("run"),
                OsString::from("uvicorn"),
                OsString::from("services.api.main:app"),
                OsString::from("--host"),
                OsString::from(API_HOST),
                OsString::from("--port"),
                OsString::from(API_PORT),
            ],
            workspace_root: workspace_root.to_path_buf(),
            pythonpath: Some(build_pythonpath(workspace_root)),
        };
    }

    if let Some(program) = command_from_path("python") {
        return LaunchPlan {
            program,
            args: base_python_args(),
            workspace_root: workspace_root.to_path_buf(),
            pythonpath: Some(build_pythonpath(workspace_root)),
        };
    }

    LaunchPlan {
        program: PathBuf::from("python"),
        args: base_python_args(),
        workspace_root: workspace_root.to_path_buf(),
        pythonpath: Some(build_pythonpath(workspace_root)),
    }
}

fn base_python_args() -> Vec<OsString> {
    vec![
        OsString::from("-m"),
        OsString::from("uvicorn"),
        OsString::from("services.api.main:app"),
        OsString::from("--host"),
        OsString::from(API_HOST),
        OsString::from("--port"),
        OsString::from(API_PORT),
    ]
}

fn build_pythonpath(workspace_root: &Path) -> OsString {
    let separator = if cfg!(windows) { ";" } else { ":" };
    OsString::from(format!(
        "{}{separator}{}",
        workspace_root.display(),
        workspace_root.join("packages").join("daysync_core").join("src").display()
    ))
}

fn command_from_path(program: &str) -> Option<PathBuf> {
    let path_var = env::var_os("PATH")?;
    let executable_names = if cfg!(windows) {
        vec![format!("{program}.exe"), format!("{program}.cmd"), format!("{program}.bat")]
    } else {
        vec![program.to_string()]
    };

    for directory in env::split_paths(&path_var) {
        for executable_name in &executable_names {
            let candidate = directory.join(executable_name);
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }
    None
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![ensure_dev_api])
        .run(tauri::generate_context!())
        .expect("failed to run DaySync desktop");
}

#[cfg(test)]
mod tests {
    use super::{
        api_matches_workspace, build_launch_plan, build_pythonpath, is_workspace_root, normalize_path_like,
        workspace_root_candidates, HealthFfmpeg, HealthResponse, RUNTIME_DIR_NAME,
    };
    use std::{fs, path::Path};

    fn create_workspace_root(path: &Path) {
        fs::create_dir_all(path.join("services").join("api")).expect("create services");
        fs::create_dir_all(path.join("packages").join("daysync_core").join("src").join("daysync_core"))
            .expect("create package");
        fs::create_dir_all(path.join("tools").join("ffmpeg").join("windows-x64")).expect("create ffmpeg root");
        fs::write(path.join("services").join("api").join("main.py"), "app = None").expect("write api main");
        fs::write(path.join("pyproject.toml"), "[project]\nname='daysync'\n").expect("write pyproject");
    }

    #[test]
    fn detects_workspace_root_from_runtime_sibling() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let release_root = temp_dir.path().join("portable");
        let runtime_root = release_root.join(RUNTIME_DIR_NAME);
        create_workspace_root(&runtime_root);
        let exe_path = release_root.join("DaySync.exe");
        fs::create_dir_all(&release_root).expect("release root");
        fs::write(&exe_path, []).expect("exe placeholder");

        let candidates = workspace_root_candidates(&exe_path, None);

        assert!(candidates.iter().any(|candidate| candidate == &runtime_root));
        assert!(is_workspace_root(&runtime_root));
    }

    #[test]
    fn detects_workspace_root_from_ancestor_repo() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let workspace_root = temp_dir.path().join("daysync");
        create_workspace_root(&workspace_root);
        let exe_path = workspace_root
            .join("apps")
            .join("desktop")
            .join("src-tauri")
            .join("target")
            .join("release")
            .join("daysync_desktop.exe");
        fs::create_dir_all(exe_path.parent().expect("exe parent")).expect("create exe parent");
        fs::write(&exe_path, []).expect("exe placeholder");

        let candidates = workspace_root_candidates(&exe_path, None);

        assert!(candidates.iter().any(|candidate| candidate == &workspace_root));
    }

    #[test]
    fn bundled_python_launch_plan_prefers_local_venv() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let workspace_root = temp_dir.path().join("daysync_runtime");
        create_workspace_root(&workspace_root);
        let python_path = workspace_root.join(".venv").join("Scripts").join("python.exe");
        fs::create_dir_all(python_path.parent().expect("python parent")).expect("create python parent");
        fs::write(&python_path, []).expect("python placeholder");

        let plan = build_launch_plan(&workspace_root);

        assert_eq!(plan.program, python_path);
        assert_eq!(plan.workspace_root, workspace_root);
        assert_eq!(plan.pythonpath, Some(build_pythonpath(&plan.workspace_root)));
    }

    #[test]
    fn normalizes_extended_length_windows_paths() {
        assert_eq!(
            normalize_path_like(r"\\?\D:\Demo\tools\ffmpeg\windows-x64"),
            r"d:\demo\tools\ffmpeg\windows-x64"
        );
    }

    #[test]
    fn detects_health_workspace_match_from_ffmpeg_root() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let workspace_root = temp_dir.path().join("daysync_runtime");
        create_workspace_root(&workspace_root);
        let health = HealthResponse {
            ffmpeg: HealthFfmpeg {
                root_path: format!(
                    r"\\?\{}",
                    workspace_root.join("tools").join("ffmpeg").join("windows-x64").display()
                ),
            },
        };

        assert!(api_matches_workspace(&health, &workspace_root));
    }
}
