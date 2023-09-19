@echo off
setlocal enabledelayedexpansion

set targetDir=../scripts/scriptFolders

for /r %targetDir% %%i in (*.zip) do (
    set "file=%%i"
    for /f %%a in ('certutil -hashfile "!file!" SHA256 ^| find /v "hash" ^| find /v "CertUtil"') do (
        echo !file! : %%a
    )
)

endlocal
