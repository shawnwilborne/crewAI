# AddBates.ps1
# PowerShell script for adding Bates numbering to PDF files
# Requires PDF processing capabilities via system tools

param(
    [Parameter(Mandatory=$true)]
    [string]$FilePath,
    
    [Parameter(Mandatory=$false)]
    [string]$FolderPath,
    
    [Parameter(Mandatory=$false)]
    [int]$StartNumber = 1,
    
    [Parameter(Mandatory=$false)]
    [string]$Prefix = "BATES",
    
    [Parameter(Mandatory=$false)]
    [string]$Position = "bottom_right",
    
    [Parameter(Mandatory=$false)]
    [switch]$DryRun,
    
    [Parameter(Mandatory=$false)]
    [switch]$Verbose
)

Write-Host "Automated Document Workflows - Bates Numbering Tool" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "DRY RUN MODE - No files will be modified" -ForegroundColor Yellow
}

# Function to add Bates numbering to a single PDF
function Add-BatesToPDF {
    param(
        [string]$File,
        [int]$Number,
        [string]$BatesPrefix,
        [string]$BatesPosition
    )
    
    $batesNumber = "$BatesPrefix$($Number.ToString().PadLeft(6, '0'))"
    
    if ($Verbose) {
        Write-Host "Processing: $File -> $batesNumber" -ForegroundColor Gray
    }
    
    if (-not $DryRun) {
        # This would integrate with the Python CLI or API
        $pythonCmd = "python cli.py bates `"$File`" --start $Number --prefix `"$BatesPrefix`" --position $BatesPosition --apply"
        
        if ($Verbose) {
            Write-Host "Command: $pythonCmd" -ForegroundColor Gray
        }
        
        try {
            Invoke-Expression $pythonCmd
            Write-Host "✓ Added Bates: $batesNumber" -ForegroundColor Green
        }
        catch {
            Write-Host "✗ Failed to process: $File" -ForegroundColor Red
            Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    else {
        Write-Host "Would add Bates: $batesNumber to $File" -ForegroundColor Yellow
    }
}

# Process files
$currentNumber = $StartNumber
$processedCount = 0

if ($FilePath) {
    # Single file processing
    if (Test-Path $FilePath) {
        Add-BatesToPDF -File $FilePath -Number $currentNumber -BatesPrefix $Prefix -BatesPosition $Position
        $processedCount = 1
    }
    else {
        Write-Host "File not found: $FilePath" -ForegroundColor Red
        exit 1
    }
}
elseif ($FolderPath) {
    # Batch processing
    if (Test-Path $FolderPath) {
        $pdfFiles = Get-ChildItem -Path $FolderPath -Filter "*.pdf" -Recurse
        
        Write-Host "Found $($pdfFiles.Count) PDF files to process" -ForegroundColor Cyan
        
        foreach ($file in $pdfFiles) {
            Add-BatesToPDF -File $file.FullName -Number $currentNumber -BatesPrefix $Prefix -BatesPosition $Position
            $currentNumber++
            $processedCount++
        }
    }
    else {
        Write-Host "Folder not found: $FolderPath" -ForegroundColor Red
        exit 1
    }
}
else {
    Write-Host "Either -FilePath or -FolderPath must be specified" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Bates numbering completed!" -ForegroundColor Green
Write-Host "Files processed: $processedCount" -ForegroundColor Cyan
Write-Host "Starting number: $StartNumber" -ForegroundColor Cyan
Write-Host "Ending number: $($currentNumber - 1)" -ForegroundColor Cyan