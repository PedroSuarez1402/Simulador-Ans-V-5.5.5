Set-Location $PSScriptRoot
if (!(Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Read-Host "Error creando entorno"; exit }
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Read-Host "Error instalando dependencias"; exit }
}
.venv\Scripts\python.exe -m streamlit run app.py
