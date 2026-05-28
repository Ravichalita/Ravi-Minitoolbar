# Script para empacotar a extensão Mini Toolbar do LibreOffice de forma compatível
# Força explicitamente o uso de barras normais ('/') em todas as entradas do arquivo ZIP.

$SrcDir = Join-Path $PSScriptRoot "mini_toolbar_extension"
$DestFiles = @(
    (Join-Path $PSScriptRoot "MiniToolbar.oxt")
)

# Tenta fechar processos do LibreOffice se estiverem travando os arquivos
try {
    Write-Host "Fechando instâncias do LibreOffice para liberar arquivos..." -ForegroundColor Cyan
    taskkill /f /im soffice.exe 2>$null
    taskkill /f /im soffice.bin 2>$null
    # Aguarda 1.5 segundos para garantir que o SO finalizou os processos e liberou as travas de arquivo
    Start-Sleep -Milliseconds 1500
} catch {}

# Adiciona o assembly necessário do .NET
Add-Type -AssemblyName System.IO.Compression

foreach ($DestOxt in $DestFiles) {
    if (Test-Path $DestOxt) {
        Write-Host "Removendo pacote anterior: $(Split-Path $DestOxt -Leaf)..."
        Remove-Item $DestOxt -Force
    }

    Write-Host "Empacotando '$SrcDir' em '$DestOxt'..."
    try {
        $zipStream = New-Object System.IO.FileStream($DestOxt, [System.IO.FileMode]::Create)
        $zipArchive = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)

        Get-ChildItem -Path $SrcDir -Recurse -File | ForEach-Object {
            $fullPath = $_.FullName
            # Calcula o caminho relativo
            $relPath = $fullPath.Substring($SrcDir.Length + 1)
            
            # FORÇA barras normais ('/') nas entradas do ZIP, eliminando o erro de ZipException no LibreOffice!
            $zipEntryName = $relPath.Replace("\", "/")
            
            $entry = $zipArchive.CreateEntry($zipEntryName)
            $entryStream = $entry.Open()
            
            $fileStream = New-Object System.IO.FileStream($fullPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read)
            $fileStream.CopyTo($entryStream)
            
            $fileStream.Close()
            $entryStream.Close()
        }

        $zipArchive.Dispose()
        $zipStream.Close()
        
        Write-Host "Pacote $(Split-Path $DestOxt -Leaf) gerado com sucesso com compatibilidade garantida!" -ForegroundColor Green
    } catch {
        Write-Error "Falha ao gerar o pacote $(Split-Path $DestOxt -Leaf): $_"
    }
}
