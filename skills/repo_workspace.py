"""Guarded local Git workspace for JARVIS development tasks."""
import os
import json
import re
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen
from pathlib import Path

BASE_DIR = Path.home() / "jarvis"
DEFAULT_CANDIDATES = (Path.home() / "JarvisOwn", BASE_DIR / "workspace")
MAX_OUTPUT = 12000
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,79}$")


def repository_path():
    configured = os.getenv("JARVIS_REPO_PATH", "").strip()
    candidates = (Path(configured).expanduser(),) if configured else DEFAULT_CANDIDATES
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate.resolve()
    return None


def _run(args, *, timeout=30):
    repo = repository_path()
    if repo is None:
        return {"ok": False, "error": "Nie znaleziono repozytorium. Ustaw JARVIS_REPO_PATH."}
    try:
        result = subprocess.run(args, cwd=repo, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Operacja przekroczyła limit {timeout} s."}
    output = (result.stdout + result.stderr).strip()
    return {"ok": result.returncode == 0, "code": result.returncode, "output": output[-MAX_OUTPUT:]}


def status():
    repo = repository_path()
    if repo is None:
        return {"ok": False, "error": "Nie znaleziono repozytorium. Ustaw JARVIS_REPO_PATH."}
    result = _run(["git", "status", "--short", "--branch"])
    result["path"] = str(repo)
    return result


def branches():
    result = _run(["git", "branch", "--list", "--no-color"])
    if result["ok"]:
        result["branches"] = [line.strip().lstrip("*").strip() for line in result["output"].splitlines() if line.strip()]
    return result


def _safe_branch(name):
    name = (name or "").strip()
    if not name or not BRANCH_RE.fullmatch(name) or ".." in name or name.endswith(".") or name.endswith("/"):
        raise ValueError("Nieprawidłowa nazwa gałęzi.")
    if name in {"main", "master", "HEAD"} or name.startswith(("main/", "master/")):
        raise ValueError("JARVIS nie tworzy ani nie modyfikuje chronionych gałęzi main/master.")
    return name if "/" in name else "jarvis/" + name


def create_branch(name):
    try:
        name = _safe_branch(name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return _run(["git", "switch", "-c", name])


def diff():
    return _run(["git", "diff", "--", "."])


def log():
    return _run(["git", "log", "-5", "--oneline", "--decorate"])


def _secret_scan():
    repo = repository_path()
    if repo is None:
        return "Nie znaleziono repozytorium."
    listing = subprocess.run(["git", "status", "--porcelain"], cwd=repo, text=True, capture_output=True, check=False)
    for line in listing.stdout.splitlines():
        relative = line[3:].strip().strip('"')
        if not relative or relative == "deleted":
            continue
        path = repo / relative
        if path.name in {".env", ".env.local", "id_rsa"} or path.suffix in {".pem", ".key"}:
            return f"Plik {relative} wygląda na sekret i nie zostanie dodany."
        if path.is_file() and path.stat().st_size <= 300000:
            content = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in content for marker in ("GROQ_API_KEY=", "github_pat_", "ghp_", "BEGIN PRIVATE KEY")):
                return f"Plik {relative} zawiera wzorzec sekretu i nie zostanie dodany."
    return None


def commit_changes(message):
    message = (message or "").strip()
    if not message or len(message) > 120 or "\n" in message:
        return {"ok": False, "error": "Podaj jednozdaniowy opis zmiany do 120 znaków."}
    current = _run(["git", "branch", "--show-current"])
    branch = current.get("output", "").strip()
    if not branch or branch in {"main", "master"}:
        return {"ok": False, "error": "Commit z main/master jest zablokowany. Utwórz gałąź jarvis/*."}
    secret = _secret_scan()
    if secret:
        return {"ok": False, "error": secret}
    tests = run_tests()
    if not tests["ok"]:
        return {"ok": False, "error": "Commit zatrzymany: testy nie przeszły.", "tests": tests}
    staged = _run(["git", "add", "-A"])
    if not staged["ok"]:
        return {"ok": False, "error": staged.get("output", "Nie udało się przygotować zmian.")}
    committed = _run(["git", "commit", "-m", message])
    if not committed["ok"]:
        return {"ok": False, "error": committed.get("output", "Nie udało się utworzyć commita.")}
    return {"ok": True, "branch": branch, "output": committed.get("output", "")}


def run_tests():
    compile_result = _run(["python", "-m", "compileall", "-q", "main.py", "jarvis_gui.py", "skills", "tests"], timeout=90)
    if not compile_result["ok"]:
        return {"ok": False, "stage": "compile", **compile_result}
    tests = _run(["python", "-m", "unittest", "discover", "-s", "tests", "-q"], timeout=180)
    return {"stage": "tests", **tests}


def write_file(relative_path, content):
    repo = repository_path()
    if repo is None:
        return {"ok": False, "error": "Nie znaleziono repozytorium."}
    relative_path = (relative_path or "").strip()
    if not relative_path or Path(relative_path).is_absolute() or "\\" in relative_path:
        return {"ok": False, "error": "Ścieżka musi być względna względem repozytorium."}
    target = (repo / relative_path).resolve()
    try:
        target.relative_to(repo)
    except ValueError:
        return {"ok": False, "error": "Nie można zapisywać poza repozytorium."}
    if ".git" in target.relative_to(repo).parts:
        return {"ok": False, "error": "Nie można edytować katalogu .git."}
    if not isinstance(content, str) or len(content) > 200000:
        return {"ok": False, "error": "Plik przekracza limit 200000 znaków."}
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(target)
    return {"ok": True, "path": str(target.relative_to(repo))}


def push_branch():
    if os.getenv("JARVIS_REPO_PUSH_ENABLED", "0") != "1":
        return {"ok": False, "error": "Push jest wyłączony. Ustaw JARVIS_REPO_PUSH_ENABLED=1 po skonfigurowaniu dostępu GitHub."}
    current = _run(["git", "branch", "--show-current"])
    branch = current.get("output", "").strip()
    if not branch or branch in {"main", "master"}:
        return {"ok": False, "error": "Push z main/master jest zablokowany."}
    return _run(["git", "push", "--set-upstream", "origin", branch], timeout=120)


def start_task(name):
    """Start an isolated Jarvis task branch."""
    try:
        branch = _safe_branch(name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    current = _run(["git", "status", "--porcelain"])
    if not current["ok"]:
        return current
    if current.get("output"):
        return {"ok": False, "error": "Repozytorium ma niezapisane zmiany. Najpierw je zatwierdź albo wyczyść."}
    return _run(["git", "switch", "-c", branch])


def _github_repo():
    configured = os.getenv("JARVIS_GITHUB_REPO", "").strip()
    if configured:
        return configured
    remote = _run(["git", "remote", "get-url", "origin"])
    value = remote.get("output", "").strip().removesuffix(".git")
    match = re.search(r"github\.com[:/]([^/]+/[^/]+)$", value)
    return match.group(1) if match else ""


def _github_request(method, url, payload=None):
    token = os.getenv("JARVIS_GITHUB_TOKEN", "").strip()
    if not token:
        return {"ok": False, "error": "Brak JARVIS_GITHUB_TOKEN."}
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "JARVIS-repo-workflow",
    })
    try:
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {"ok": True, "data": data}
    except Exception as exc:
        return {"ok": False, "error": f"GitHub API: {exc}"}


def _wait_for_ci(repo, sha):
    timeout = max(30, int(os.getenv("JARVIS_CI_TIMEOUT_SECONDS", "900")))
    interval = max(3, int(os.getenv("JARVIS_CI_POLL_SECONDS", "10")))
    deadline = time.monotonic() + timeout
    url = f"https://api.github.com/repos/{repo}/actions/runs?head_sha={sha}&per_page=10"
    while time.monotonic() < deadline:
        result = _github_request("GET", url)
        if not result["ok"]:
            return result
        runs = result["data"].get("workflow_runs", [])
        matching = [run for run in runs if run.get("head_sha") == sha]
        if matching and all(run.get("status") == "completed" for run in matching):
            if all(run.get("conclusion") == "success" for run in matching):
                return {"ok": True, "output": "GitHub Actions zakończone sukcesem."}
            return {"ok": False, "error": "GitHub Actions zakończyły się błędem. PR pozostaje niescalony."}
        time.sleep(interval)
    return {"ok": False, "error": "Przekroczono czas oczekiwania na GitHub Actions. PR pozostaje niescalony."}


def create_and_merge_pr(message):
    if os.getenv("JARVIS_GITHUB_AUTO_MERGE", "0") != "1":
        return {"ok": False, "error": "Automatyczne scalanie jest wyłączone. Ustaw JARVIS_GITHUB_AUTO_MERGE=1."}
    repo = _github_repo()
    branch = _run(["git", "branch", "--show-current"]).get("output", "").strip()
    if not repo or not branch or branch in {"main", "master"}:
        return {"ok": False, "error": "Brak repozytorium GitHub albo trwa praca na chronionej gałęzi."}
    base = os.getenv("JARVIS_GITHUB_BASE", "main")
    created = _github_request("POST", f"https://api.github.com/repos/{repo}/pulls", {
        "title": message,
        "head": branch,
        "base": base,
        "body": "PR utworzony przez JARVIS-a po przejściu lokalnych testów.",
    })
    if not created["ok"]:
        return created
    number = created["data"].get("number")
    head_sha = _run(["git", "rev-parse", "HEAD"]).get("output", "").strip()
    ci = _wait_for_ci(repo, head_sha)
    if not ci["ok"]:
        return {"ok": False, "number": number, "error": ci["error"]}
    merged = _github_request("PUT", f"https://api.github.com/repos/{repo}/pulls/{number}/merge", {
        "merge_method": "squash",
        "commit_title": message,
    })
    if merged["ok"] and merged["data"].get("merged"):
        return {"ok": True, "number": number, "output": "PR scalony do main."}
    return {"ok": False, "number": number, "error": "PR utworzony, ale GitHub nie scalił go automatycznie.", "details": merged}


def finish_task(message):
    committed = commit_changes(message)
    if not committed["ok"]:
        return committed
    pushed = push_branch()
    if not pushed["ok"]:
        return {"ok": False, "error": "Commit utworzony, ale push nie powiódł się.", "details": pushed}
    if os.getenv("JARVIS_GITHUB_AUTO_MERGE", "0") == "1":
        return create_and_merge_pr(message)
    return {"ok": True, "output": "Commit i push zakończone. Auto-merge jest wyłączony."}


def process_repo_command(text):
    lower = (text or "").strip().lower()
    if not any(marker in lower for marker in ("repo", "github", "gałąź", "galaz", "branch")):
        return None
    if any(marker in lower for marker in ("test repo", "testuj repo", "przetestuj repo", "testy repo")):
        result = run_tests()
        return "Testy repozytorium przeszły pomyślnie." if result["ok"] else f"Testy repozytorium nie przeszły: {result.get('output') or result.get('error', 'błąd')}"
    if any(marker in lower for marker in ("status repo", "status github", "stan repo")):
        result = status()
        return result.get("output") if result["ok"] else result["error"]
    if "log repo" in lower or "historia repo" in lower:
        result = log()
        return result.get("output") if result["ok"] else result["error"]
    if "doctor repo" in lower or "sprawdź repo" in lower or "sprawdz repo" in lower:
        result = run_tests()
        return "Repozytorium przeszło diagnostykę." if result["ok"] else f"Diagnostyka nie przeszła: {result.get('output') or result.get('error', 'błąd')}"
    if any(marker in lower for marker in ("branch repo", "gałęzie repo", "galazie repo")):
        result = branches()
        return "Gałęzie: " + ", ".join(result.get("branches", [])) if result["ok"] else result["error"]
    match = re.search(r"(?:utwórz|utworz|dodaj)\s+(?:branch|gałąź|galaz)\s+([A-Za-z0-9._/-]+)", lower)
    if match:
        result = create_branch(match.group(1))
        return "Utworzyłem gałąź roboczą." if result["ok"] else result["error"]
    if "diff repo" in lower or "zmiany repo" in lower:
        result = diff()
        return (result.get("output") or "Brak zmian.") if result["ok"] else result["error"]
    if "wypchnij branch" in lower or "push branch" in lower:
        result = push_branch()
        return "Wypchnąłem bieżącą gałąź." if result["ok"] else result["error"]
    match = re.search(r"(?:zacznij|rozpocznij) pracę nad repo(?:zytorium)?\s+(.+)$", lower)
    if match:
        result = start_task(match.group(1))
        return "Utworzyłem izolowaną gałąź pracy." if result["ok"] else result["error"]
    match = re.search(r"(?:zakończ|zakoncz) pracę nad repo(?:zytorium)?\s+(.+)$", lower)
    if match:
        result = finish_task(match.group(1))
        return result.get("output") if result["ok"] else result.get("error", "Workflow repozytorium nie powiódł się.")
    match = re.search(r"(?:zatwierdź|zatwierdz|commit)\s+(?:zmiany\s+)?repo(?:zytorium)?\s+(.+)$", lower)
    if match:
        result = commit_changes(match.group(1))
        return "Zmiany zatwierdzone po przejściu testów." if result["ok"] else result["error"]
    return "Mogę pokazać status, gałęzie, diff albo uruchomić lokalne testy repozytorium."
