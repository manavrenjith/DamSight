# scripts/tasks.ps1
# Mirrors targets from Makefile for Windows environments without `make`.
param (
    [Parameter(Position = 0)]
    [string]$Task = "help",
    [string]$Site = "site_a"
)

$env:PYTHONUTF8 = "1"

function Show-Help {
    Write-Host "DamSight Tasks (PowerShell Makefile Mirror):"
    Write-Host "  .\scripts\tasks.ps1 setup        - Install package in editable mode"
    Write-Host "  .\scripts\tasks.ps1 test         - Run test suite"
    Write-Host "  .\scripts\tasks.ps1 lint         - Run code linter"
    Write-Host "  .\scripts\tasks.ps1 ingest       - Ingest terrain and exposure datasets"
    Write-Host "  .\scripts\tasks.ps1 run-site     - Run hydrodynamic simulation for site"
    Write-Host "  .\scripts\tasks.ps1 ensemble     - Run Monte Carlo ensemble"
    Write-Host "  .\scripts\tasks.ps1 surrogate    - Train ML surrogate model"
    Write-Host "  .\scripts\tasks.ps1 evac         - Run evacuation routing analysis"
    Write-Host "  .\scripts\tasks.ps1 precompute   - Generate precomputed demo outputs"
    Write-Host "  .\scripts\tasks.ps1 demo         - Launch API server and web dashboard"
}

switch ($Task.ToLower()) {
    "setup" {
        python -m pip install -e . --no-deps
    }
    "test" {
        pytest tests/
    }
    "lint" {
        python -m ruff check src/ tests/
    }
    "ingest" {
        python scripts/run_site.py --site $Site --stage ingest --allow-synthetic
    }
    "run-site" {
        Write-Host "not implemented yet"
    }
    "ensemble" {
        Write-Host "not implemented yet"
    }
    "surrogate" {
        Write-Host "not implemented yet"
    }
    "evac" {
        Write-Host "not implemented yet"
    }
    "precompute" {
        Write-Host "not implemented yet"
    }
    "demo" {
        Write-Host "not implemented yet"
    }
    "help" {
        Show-Help
    }
    default {
        Write-Warning "Unknown task: $Task"
        Show-Help
    }
}
