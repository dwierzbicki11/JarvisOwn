from pathlib import Path
import sys

try:
    import openwakeword
except Exception as exc:
    print(f"BŁĄD importu openWakeWord: {exc}")
    sys.exit(1)


def exists():
    if hasattr(openwakeword, "MODELS"):
        entry = openwakeword.MODELS.get("hey_jarvis", {})
        path = entry.get("model_path")

        if path and Path(path).exists():
            return Path(path)

        if path:
            onnx = Path(str(path).replace(".tflite", ".onnx"))

            if onnx.exists():
                return onnx

    if hasattr(openwakeword, "models"):
        entry = openwakeword.models.get("hey_jarvis", {})
        path = entry.get("model_path")

        if path and Path(path).exists():
            return Path(path)

    return None


found = exists()

if found:
    print(f"OK - model już istnieje: {found}")
    sys.exit(0)


print("Modelu nie ma lokalnie. Próbuję pobrać...")

try:
    from openwakeword import utils

    try:
        utils.download_models(["hey_jarvis"])
    except TypeError:
        utils.download_models()

except Exception as exc:
    print(f"BŁĄD pobierania modeli: {exc}")
    sys.exit(2)


found = exists()

if not found:
    print(
        "Pobieranie zakończone, ale model hey_jarvis "
        "nadal nie został znaleziony."
    )
    sys.exit(3)

print(f"OK - model gotowy: {found}")
