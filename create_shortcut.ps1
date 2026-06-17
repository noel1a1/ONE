$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath('Desktop')
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\ONE.lnk")
$Shortcut.TargetPath = "d:\The App\ONE\start.bat"
$Shortcut.WorkingDirectory = "d:\The App\ONE"
$Shortcut.Description = "Launch ONE - Platform"
$Shortcut.IconLocation = "shell32.dll,13"
$Shortcut.Save()
Write-Host "Shortcut successfully created at $DesktopPath\ONE.lnk"
