# Overnight eval resumer wrapper (invoked by scheduled tasks BEE-eval-resume-1..3).
# Idempotent: eval_resume.py skips already-passed tasks; per-task persistence.
Set-Location "C:\Users\mshri\OneDrive\Desktop\PA"
$log = Join-Path (Get-Location) "evals\eval_resume.log"
Add-Content -Path $log -Value ("===== run at " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " =====")
python eval_resume.py 2>&1 | Tee-Object -FilePath $log -Append
Add-Content -Path $log -Value ("===== exit " + $LASTEXITCODE + " =====")
