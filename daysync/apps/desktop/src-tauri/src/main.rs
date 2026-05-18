#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    env,
    ffi::OsString,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStderr, ChildStdin, ChildStdout, Command, Stdio},
    sync::Mutex,
};
use tauri::State;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

const WORKSPACE_ENV_KEY: &str = "DAYSYNC_WORKSPACE_ROOT";
const RUNTIME_DIR_NAME: &str = "daysync_runtime";

#[derive(Debug, Clone, PartialEq, Eq)]
struct LaunchPlan {
    program: PathBuf,
    args: Vec<OsString>,
    workspace_root: PathBuf,
    pythonpath: Option<OsString>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct RuntimeErrorPayload {
    code: String,
    message: String,
    #[serde(default)]
    details: Value,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct RuntimeCommandResponse {
    ok: bool,
    #[serde(default)]
    result: Option<Value>,
    #[serde(default)]
    error: Option<RuntimeErrorPayload>,
}

#[derive(Debug, Serialize, Deserialize)]
struct WorkerRequest {
    id: u64,
    method: String,
    payload: Value,
}

#[derive(Debug, Serialize, Deserialize)]
struct WorkerResponse {
    id: u64,
    ok: bool,
    #[serde(default)]
    result: Option<Value>,
    #[serde(default)]
    error: Option<RuntimeErrorPayload>,
}

struct RuntimeProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    #[allow(dead_code)]
    stderr: BufReader<ChildStderr>,
    next_id: u64,
}

impl RuntimeProcess {
    fn spawn(plan: &LaunchPlan) -> Result<Self, String> {
        let mut command = Command::new(&plan.program);
        command
            .args(&plan.args)
            .current_dir(&plan.workspace_root)
            .env(WORKSPACE_ENV_KEY, &plan.workspace_root)
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUTF8", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        if let Some(pythonpath) = &plan.pythonpath {
            command.env("PYTHONPATH", pythonpath);
        }

        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);

        let mut child = command
            .spawn()
            .map_err(|error| format!("Failed to start local runtime worker: {error}"))?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "Failed to open runtime worker stdin.".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "Failed to open runtime worker stdout.".to_string())?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| "Failed to open runtime worker stderr.".to_string())?;

        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            stderr: BufReader::new(stderr),
            next_id: 0,
        })
    }

    fn is_running(&mut self) -> Result<bool, String> {
        self.child
            .try_wait()
            .map(|status| status.is_none())
            .map_err(|error| format!("Failed to inspect runtime worker state: {error}"))
    }

    fn terminate(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }

    fn call(&mut self, method: &str, payload: Value) -> Result<RuntimeCommandResponse, String> {
        if !self.is_running()? {
            return Err("Runtime worker exited before request was sent.".to_string());
        }

        self.next_id += 1;
        let request = WorkerRequest {
            id: self.next_id,
            method: method.to_string(),
            payload,
        };
        let serialized =
            serde_json::to_string(&request).map_err(|error| format!("Failed to encode runtime request: {error}"))?;
        self.stdin
            .write_all(serialized.as_bytes())
            .map_err(|error| format!("Failed to write runtime request: {error}"))?;
        self.stdin
            .write_all(b"\n")
            .map_err(|error| format!("Failed to terminate runtime request line: {error}"))?;
        self.stdin
            .flush()
            .map_err(|error| format!("Failed to flush runtime request: {error}"))?;

        let mut line = String::new();
        let bytes = self
            .stdout
            .read_line(&mut line)
            .map_err(|error| format!("Failed to read runtime response: {error}"))?;
        if bytes == 0 {
            return Err("Runtime worker closed stdout before responding.".to_string());
        }

        let response: WorkerResponse = serde_json::from_str(line.trim_end())
            .map_err(|error| format!("Failed to parse runtime response: {error}"))?;
        if response.id != request.id {
            return Err(format!(
                "Runtime response id mismatch: expected {}, received {}.",
                request.id, response.id
            ));
        }

        Ok(RuntimeCommandResponse {
            ok: response.ok,
            result: response.result,
            error: response.error,
        })
    }
}

struct AppRuntime {
    launch_plan: LaunchPlan,
    process: Mutex<Option<RuntimeProcess>>,
}

impl AppRuntime {
    fn new() -> Result<Self, String> {
        let current_exe =
            env::current_exe().map_err(|error| format!("Failed to resolve current executable: {error}"))?;
        let workspace_root = resolve_workspace_root(&current_exe)?;
        Ok(Self {
            launch_plan: build_launch_plan(&workspace_root),
            process: Mutex::new(None),
        })
    }

    fn call(&self, method: &str, payload: Value) -> RuntimeCommandResponse {
        match self.call_with_retry(method, payload.clone(), true) {
            Ok(response) => response,
            Err(first_error) => runtime_unavailable_response(first_error),
        }
    }

    fn call_with_retry(
        &self,
        method: &str,
        payload: Value,
        allow_restart: bool,
    ) -> Result<RuntimeCommandResponse, String> {
        let mut guard = self
            .process
            .lock()
            .map_err(|_| "Failed to lock local runtime manager.".to_string())?;
        ensure_process(&self.launch_plan, &mut guard)?;

        let first_response = guard
            .as_mut()
            .ok_or_else(|| "Local runtime process was not created.".to_string())?
            .call(method, payload.clone());

        match first_response {
            Ok(response) => Ok(response),
            Err(_error) if allow_restart => {
                replace_process(&self.launch_plan, &mut guard)?;
                guard
                    .as_mut()
                    .ok_or_else(|| "Local runtime process was not recreated.".to_string())?
                    .call(method, payload)
            }
            Err(error) => Err(error),
        }
    }
}

#[tauri::command]
fn ensure_runtime_ready(runtime: State<'_, AppRuntime>) -> RuntimeCommandResponse {
    runtime.call("health.check", json!({}))
}

#[tauri::command]
fn invoke_runtime(
    runtime: State<'_, AppRuntime>,
    method: String,
    payload: Value,
) -> RuntimeCommandResponse {
    runtime.call(&method, payload)
}

fn runtime_unavailable_response(message: String) -> RuntimeCommandResponse {
    RuntimeCommandResponse {
        ok: false,
        result: None,
        error: Some(RuntimeErrorPayload {
            code: "RUNTIME_UNAVAILABLE".to_string(),
            message: "未能连接本地运行时，请稍后重试。".to_string(),
            details: json!({ "cause": message }),
        }),
    }
}

fn ensure_process(plan: &LaunchPlan, process: &mut Option<RuntimeProcess>) -> Result<(), String> {
    if let Some(existing) = process.as_mut() {
        if existing.is_running()? {
            return Ok(());
        }
        existing.terminate();
    }
    *process = Some(RuntimeProcess::spawn(plan)?);
    Ok(())
}

fn replace_process(plan: &LaunchPlan, process: &mut Option<RuntimeProcess>) -> Result<(), String> {
    if let Some(existing) = process.as_mut() {
        existing.terminate();
    }
    *process = Some(RuntimeProcess::spawn(plan)?);
    Ok(())
}

fn resolve_workspace_root(current_exe: &Path) -> Result<PathBuf, String> {
    if let Ok(value) = env::var(WORKSPACE_ENV_KEY) {
        let candidate = PathBuf::from(value);
        if is_workspace_root(&candidate) {
            return candidate
                .canonicalize()
                .map_err(|error| format!("Failed to canonicalize workspace root '{}': {error}", candidate.display()));
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
        OsString::from("daysync_core.bridge.worker"),
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
    let runtime = AppRuntime::new().expect("failed to initialize local runtime manager");
    tauri::Builder::default()
        .manage(runtime)
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![ensure_runtime_ready, invoke_runtime])
        .run(tauri::generate_context!())
        .expect("failed to run DaySync desktop");
}

#[cfg(test)]
mod tests {
    use super::{base_python_args, build_launch_plan, build_pythonpath, is_workspace_root, workspace_root_candidates, RUNTIME_DIR_NAME};
    use std::{fs, path::Path};

    fn create_workspace_root(path: &Path) {
        fs::create_dir_all(path.join("packages").join("daysync_core").join("src").join("daysync_core"))
            .expect("create package");
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
        assert_eq!(plan.args, base_python_args());
    }
}
