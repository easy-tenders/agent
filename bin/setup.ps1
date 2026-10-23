# setup - подготовить чистую машину Windows. macOS / Linux - bin/setup.
#
# Executor of meta-vault/operations/add-engine.md и шага «первый запуск».
# Запуск из корня неймспейса:
#   powershell -ExecutionPolicy Bypass -File bin\setup.ps1
# Что делает: git и Python 3.10+ через winget (если их нет, в профиль
# пользователя, без прав администратора); если есть движок
# (engine\pyproject.toml или engine\requirements.txt) - .venv в корне и
# зависимости; системные пакеты движка - engine\setup-extra.ps1, если есть;
# проверяет длинные пути; создаёт secrets\ (вне git); в конце - bin\check.
# Повторный запуск безопасен: ставит только недостающее.
# Файл сохранён в UTF-8 с BOM: иначе Windows PowerShell 5.1 ломает кириллицу.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "setup: $(Get-Location)"

function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
              [Environment]::GetEnvironmentVariable('Path', 'Machine')
}
function Winget-Install($id) {
  if (-not (Have 'winget')) { throw "нет winget: поставьте $id вручную и запустите setup снова" }
  winget install -e --id $id --scope user --accept-source-agreements --accept-package-agreements
  Refresh-Path
}

if (-not (Have 'git')) { Winget-Install 'Git.Git' }

function Find-Python {
  foreach ($c in @('py', 'python', 'python3')) {
    if (Have $c) {
      & $c -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { return $c }
    }
  }
  $local = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
  if (Test-Path $local) { return $local }
  return $null
}
$py = Find-Python
if (-not $py) { Winget-Install 'Python.Python.3.12'; $py = Find-Python }
if (-not $py) { throw 'Python 3.10+ не найден после установки: откройте новое окно PowerShell и запустите setup снова' }
Write-Host "python: $(& $py --version)"

# Длинные пути: без них Windows не создаёт файлы глубже 260 символов.
$lp = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -ErrorAction SilentlyContinue).LongPathsEnabled
if ($lp -ne 1) {
  Write-Host 'внимание: длинные пути выключены (LongPathsEnabled = 0).'
  Write-Host '  включает владелец машины, с правами администратора - см. meta-vault/forms/handover-door-form.md'
}
if (Test-Path '.git') { git config core.longpaths true }

if ((Test-Path 'engine\pyproject.toml') -or (Test-Path 'engine\requirements.txt')) {
  if (-not (Test-Path '.venv')) { & $py -m venv .venv }
  $vpy = '.venv\Scripts\python.exe'
  & $vpy -m pip install -q --upgrade pip
  if (Test-Path 'engine\pyproject.toml') { & $vpy -m pip install -q -e engine }
  else { & $vpy -m pip install -q -r engine\requirements.txt }
  if (Test-Path 'engine\setup-extra.ps1') { & 'engine\setup-extra.ps1' }
  Write-Host 'движок: .venv готов'
} else {
  Write-Host 'движка нет - ставить нечего'
}

New-Item -ItemType Directory -Force -Path 'secrets' | Out-Null
if (-not (Test-Path 'secrets\goszakup-token') -or (Get-Item 'secrets\goszakup-token').Length -eq 0) {
  Write-Host 'токен портала не положен: secrets\goszakup-token (одна строка; откуда взять - meta-vault/secrets-map.md).'
  Write-Host '  без него поиск лотов идёт по сайту портала, медленнее; проверка - py engine\scripts\ows.py check'
}
& $py bin\check --quiet
if ($LASTEXITCODE -ne 0) { Write-Host 'bin\check нашёл, что поправить - запустите без --quiet' }
Write-Host 'готово'
