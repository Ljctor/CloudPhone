//! The fake emulator behind a test's gateway (`tests/fake-emulator`).
//!
//! [`Fake::start`] prepares the build once per test binary
//! (`tests/fake-emulator/prepare.sh`), then starts `fake_emulator.py` in a
//! fresh directory; the fake starts the repository's gateway on a free port
//! and restarts it when it exits, as systemd does in production. Dropping
//! the `Fake` stops both and removes the directory (kept with
//! `CLOUDPHONE_E2E_KEEP=1`). When a test fails, the end of the fake's and
//! the gateway's logs is printed.
//!
//! What the fake received (`record`) and the states it can be put in
//! (`control`) are documented in `fake_emulator.py`.

use serde_json::{json, Value};
use std::io::{BufRead, BufReader};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Mutex, Once};
use std::time::{Duration, Instant};

static PREPARE: Once = Once::new();
static COUNTER: AtomicU32 = AtomicU32::new(0);

pub struct Fake {
    child: Mutex<Child>,
    /// The gateway's port: the page is at http://127.0.0.1:PORT/.
    pub web_port: u16,
    control: String,
    workdir: PathBuf,
}

/// The repository's root (tests/e2e/../..).
pub fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().expect("repository root")
}

fn prepare() {
    PREPARE.call_once(|| {
        let script = repo_root().join("tests/fake-emulator/prepare.sh");
        let status = Command::new(&script).stdin(Stdio::null()).status().unwrap_or_else(|e| panic!("{}: {e}", script.display()));
        assert!(status.success(), "{} failed: {status}", script.display());
    });
}

impl Fake {
    pub fn start(config: Value) -> Fake {
        prepare();
        let root = repo_root();
        let build = root.join("build/e2e");
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let workdir = std::env::temp_dir().join(format!("cloudphone-e2e-{}-{n}", std::process::id()));
        let _ = std::fs::remove_dir_all(&workdir);
        std::fs::create_dir_all(&workdir).expect("fake's directory");
        let log = std::fs::File::create(workdir.join("fake.log")).expect("fake's log");
        let mut command = Command::new(build.join("venv-fake/bin/python"));
        command
            .arg("-B")
            .arg(root.join("tests/fake-emulator/fake_emulator.py"))
            .arg("--workdir")
            .arg(&workdir)
            .arg("--proto-dir")
            .arg(build.join("gateway/videobridge_gateway/proto"))
            .arg("--gateway-python")
            .arg(build.join("venv-gateway/bin/python"))
            .arg("--gateway-path")
            .arg(build.join("gateway"))
            .arg("--web-root")
            .arg(build.join("web"))
            .arg("--config")
            .arg(config.to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(log)
            .process_group(0);
        unsafe {
            // Killed with the test thread that started it, whatever happens.
            command.pre_exec(|| {
                libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL);
                Ok(())
            });
        }
        let mut child = command.spawn().expect("start the fake emulator (run tests/fake-emulator/prepare.sh?)");
        let stdout = child.stdout.take().unwrap();
        let (sender, receiver) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Some(ready) = line.strip_prefix("READY ") {
                    let _ = sender.send(ready.to_string());
                }
            }
        });
        let fake_log = workdir.join("fake.log");
        let ready = match receiver.recv_timeout(Duration::from_secs(90)) {
            Ok(ready) => ready,
            Err(_) => {
                let _ = child.kill();
                panic!("the fake emulator did not start:\n{}", tail(&fake_log, 40));
            }
        };
        let ready: Value = serde_json::from_str(&ready).expect("READY line");
        Fake {
            child: Mutex::new(child),
            web_port: ready["web"].as_u64().unwrap() as u16,
            control: format!("http://127.0.0.1:{}/", ready["control"]),
            workdir,
        }
    }

    fn http() -> reqwest::blocking::Client {
        reqwest::blocking::Client::builder().timeout(Duration::from_secs(30)).build().unwrap()
    }

    /// Everything the emulator received: `touches` ({x, y, identifier,
    /// pressure, touch_major, touch_minor, display, via: "touch" (data
    /// channel) | "grpc" (HTTP fallback)}), `keys` ({key, via: "keyboard" |
    /// "adb"}), `channel_messages`, `grpc` calls, `jsep` messages each way,
    /// `requests` (display and settings: requests and status lines),
    /// `sessions`, `gateway` starts and exits, `events`, `adb` calls.
    pub fn record(&self) -> Value {
        let url = format!("{}record", self.control);
        crate::off_runtime(move || Self::http().get(url).send().and_then(|r| r.json()).expect("fake /record"))
    }

    /// The fake's own state: display, settings, unit, booted, gateway...
    pub fn state(&self) -> Value {
        let url = format!("{}state", self.control);
        crate::off_runtime(move || Self::http().get(url).send().and_then(|r| r.json()).expect("fake /state"))
    }

    /// Changes the fake's state (`booted`, `unit`, `load`, `grpc`,
    /// `data_channels`, `offer`, `frames`, `touch_fails`, `adb_fails`,
    /// `hold_requests`, `fail_next`, timings...) and/or runs an `action`
    /// (`drop_streams`, `crash`, `restart`, `replace_discovery`,
    /// `stop_gateway`, `start_gateway`, `restart_gateway`, `reset_record`,
    /// `pause_gateway` with `seconds`: SIGSTOP, then SIGCONT).
    pub fn control(&self, body: Value) -> Value {
        let url = format!("{}control", self.control);
        crate::off_runtime(move || {
            let response = Self::http().post(url).json(&body).send().expect("fake /control");
            assert!(response.status().is_success(), "fake /control {body}: {}", response.status());
            response.json().unwrap()
        })
    }

    pub fn action(&self, name: &str) -> Value {
        self.control(json!({"action": name}))
    }

    /// Polls the record until `check` gives Some.
    pub fn wait_record<T>(&self, what: &str, timeout: Duration, mut check: impl FnMut(&Value) -> Option<T>) -> T {
        let start = Instant::now();
        loop {
            let record = self.record();
            if let Some(value) = check(&record) {
                return value;
            }
            if start.elapsed() > timeout {
                panic!("timed out after {timeout:?} waiting for {what}; record: {}", short(&record));
            }
            std::thread::sleep(Duration::from_millis(200));
        }
    }

    /// The touches received so far.
    pub fn touches(&self) -> Vec<Value> {
        self.record()["touches"].as_array().cloned().unwrap_or_default()
    }

    /// The keys received so far.
    pub fn keys(&self) -> Vec<Value> {
        self.record()["keys"].as_array().cloned().unwrap_or_default()
    }

    /// The end of the fake's and the gateway's logs.
    pub fn logs(&self) -> String {
        format!(
            "--- fake emulator log ---\n{}\n--- gateway log ---\n{}",
            tail(&self.workdir.join("fake.log"), 30),
            tail(&self.workdir.join("gateway.log"), 30)
        )
    }
}

fn short(record: &Value) -> String {
    let text = record.to_string();
    if text.len() > 3000 { format!("{}…", &text[..3000]) } else { text }
}

fn tail(path: &Path, lines: usize) -> String {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    let all: Vec<&str> = text.lines().collect();
    all[all.len().saturating_sub(lines)..].join("\n")
}

impl Drop for Fake {
    fn drop(&mut self) {
        if std::thread::panicking() {
            eprintln!("{}", self.logs());
        }
        let mut child = self.child.lock().unwrap_or_else(|p| p.into_inner());
        unsafe {
            libc::kill(child.id() as i32, libc::SIGTERM);
        }
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(8) {
            if let Ok(Some(_)) = child.try_wait() {
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        unsafe {
            // The fake's whole group (the gateway too, if still there).
            libc::killpg(child.id() as i32, libc::SIGKILL);
        }
        let _ = child.wait();
        if std::env::var("CLOUDPHONE_E2E_KEEP").map(|v| v == "1").unwrap_or(false) {
            eprintln!("fake emulator's files kept in {}", self.workdir.display());
        } else {
            let _ = std::fs::remove_dir_all(&self.workdir);
        }
    }
}
