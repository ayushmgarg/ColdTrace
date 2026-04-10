Set-Location $PSScriptRoot\..
python -m uvicorn backend.app.main:app --reload

