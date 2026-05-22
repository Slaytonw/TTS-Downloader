# TTS-Downloader

Python app to download Tabletop Simulator Steam Workshop items.

## Run from source

```powershell
pip install -r requirements.txt
python app.py
```

## Build a Windows executable

```powershell
.\build.ps1
```

This produces `app.dist\TTS Downloader.exe` plus the runtime DLLs. Zip the whole `app.dist\` folder and distribute that.

### About antivirus false-positives

Unsigned Nuitka/PyInstaller builds are commonly flagged by Windows Defender and other AVs. The mitigations already applied in `build.ps1`:

- `--standalone` instead of `--onefile` (onefile mimics malware packers).
- Embedded metadata (`--company-name`, `--product-name`, `--file-description`, `--file-version`).
- No `python-magic` / libmagic DLLs (replaced with built-in magic-number sniffing).

What still helps if users keep getting flags:

- **Code-sign the EXE** with an EV or OV certificate. This is the only fully reliable fix.
- **Submit the false positive** to Microsoft: https://www.microsoft.com/wdsi/filesubmission
- Distribute the zipped folder (not a renamed/repackaged single EXE).
