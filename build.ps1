$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe -m unittest -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
& .\.venv\Scripts\python.exe -c "from pathlib import Path; from hextech import make_icon; Path('assets').mkdir(exist_ok=True); make_icon().save('assets/hextech.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin --name LOLping --icon assets/hextech.ico --add-data 'champions_zh.json;.' overlay.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
