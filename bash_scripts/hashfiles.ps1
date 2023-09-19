$folderPath = "..\scripts\scriptFolders"

Get-ChildItem -Path $folderPath -Recurse -Include *.zip | ForEach-Object -Parallel {
    $hash = Get-FileHash -Path $_.FullName -Algorithm SHA256
    return "$($hash.Path) : $($hash.Hash)"
} | Out-File "hashes.txt"
