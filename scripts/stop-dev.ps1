$taskPython = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'))
Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -eq $taskPython -and
    ($_.CommandLine -match '-m uvicorn zprint\.main:app' -or
     $_.CommandLine -match '-m zprint_agent\.worker' -or
     $_.CommandLine -match '-m zprint\.maintenance')
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId
    Write-Output "Stopped Z-PRINT development process $($_.ProcessId)"
}
