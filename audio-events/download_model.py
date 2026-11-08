"""Download the small Apache-2.0 English model; never downloads at listener runtime."""

from pathlib import Path
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent / "models"
NAME = "vosk-model-small-en-us-0.15"
URL = f"https://alphacephei.com/vosk/models/{NAME}.zip"


def main():
    ROOT.mkdir(exist_ok=True)
    destination = ROOT / NAME
    if (destination / "am" / "final.mdl").is_file():
        print(f"Model already present: {destination}")
        return
    print(f"Downloading {URL} (about 40 MB)...", flush=True)
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        archive = Path(temp) / "model.zip"
        with urllib.request.urlopen(URL, timeout=120) as source, archive.open("wb") as output:
            import shutil
            shutil.copyfileobj(source, output)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (Path(temp) / member.filename).resolve()
                if not target.is_relative_to(Path(temp).resolve()) or not member.filename.startswith(NAME + "/"):
                    raise ValueError("Unsafe model archive path")
            bundle.extractall(temp)
        extracted = Path(temp) / NAME
        if not (extracted / "am" / "final.mdl").is_file():
            raise ValueError("Model archive is incomplete")
        extracted.rename(destination)
    print(f"Model ready: {destination}")


if __name__ == "__main__":
    main()
