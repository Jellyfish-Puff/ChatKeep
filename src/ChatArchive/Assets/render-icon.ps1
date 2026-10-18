Add-Type -AssemblyName PresentationCore, WindowsBase
$folder = $PSScriptRoot
[xml]$svg = Get-Content -LiteralPath (Join-Path $folder 'chat-archive.svg') -Raw
$visual = New-Object System.Windows.Media.DrawingVisual
$context = $visual.RenderOpen()
$converter = New-Object System.Windows.Media.BrushConverter
foreach ($element in $svg.DocumentElement.ChildNodes) {
    switch ($element.LocalName) {
        'rect' {
            $brush = $converter.ConvertFromString($element.fill)
            $rect = New-Object System.Windows.Rect([double]$element.x,[double]$element.y,[double]$element.width,[double]$element.height)
            $context.DrawRoundedRectangle($brush,$null,$rect,[double]$element.rx,[double]$element.rx)
        }
        'path' {
            $context.DrawGeometry($converter.ConvertFromString($element.fill),$null,[System.Windows.Media.Geometry]::Parse($element.d))
        }
        'g' {
            $brush = $converter.ConvertFromString($element.fill)
            foreach ($circle in $element.ChildNodes) {
                $point = New-Object System.Windows.Point([double]$circle.cx,[double]$circle.cy)
                $context.DrawEllipse($brush,$null,$point,[double]$circle.r,[double]$circle.r)
            }
        }
    }
}
$context.Close()
$bitmap = New-Object System.Windows.Media.Imaging.RenderTargetBitmap(1024,1024,96,96,[System.Windows.Media.PixelFormats]::Pbgra32)
$bitmap.Render($visual)
$encoder = New-Object System.Windows.Media.Imaging.PngBitmapEncoder
$encoder.Frames.Add([System.Windows.Media.Imaging.BitmapFrame]::Create($bitmap))
$file = [System.IO.File]::Create((Join-Path $folder 'chat-archive.png'))
try { $encoder.Save($file) } finally { $file.Dispose() }
