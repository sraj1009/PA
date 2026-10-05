# Batch E launcher: wait for RAM headroom, clean zombies, run 3 eval tasks.
$deadline = (Get-Date).AddMinutes(8)
while ((Get-Date) -lt $deadline) {
    $free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB)
    Write-Output "free_MB=$free"
    if ($free -ge 1500) { break }
    Start-Sleep -Seconds 10
}
[System.Diagnostics.Process]::GetProcessesByName('llama-server') | ForEach-Object {
    try { $_.Kill(); Write-Output "killed stale llama-server $($_.Id)" } catch {}
}
Start-Sleep -Seconds 3
Set-Location 'C:\Users\mshri\OneDrive\Desktop\PA'
Get-ChildItem -Recurse -Directory -Filter __pycache__ bee | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
python eval_batch.py file_list_ws dsa_lis dsa_gcd_lcm
Write-Output "BATCH_E_DONE exit=$LASTEXITCODE"
