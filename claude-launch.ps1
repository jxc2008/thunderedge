# Claude Code launcher - avoids path-with-spaces errors on Windows
# Run: .\claude-launch.ps1

$env:CLAUDE_CONFIG_DIR = "C:\claude-config"
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
claude
