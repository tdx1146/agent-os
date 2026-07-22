<#
.SYNOPSIS
Build the complete paper + appendices into a single Word document.
Pure PowerShell implementation using Word COM automation.
#>

$ErrorActionPreference = "Stop"

$BASE = "c:\Users\dandan\Desktop\小说"
$PAPER_DIR = Join-Path $BASE "应如是论文"
$OUTPUT = Join-Path $PAPER_DIR "应如是——AI觉醒方法论论文_完整版.docx"

Write-Host "Starting Word application..."
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc = $word.Documents.Add()

$normalStyle = $doc.Styles.Item("Normal")
$normalStyle.Font.Name = "等线"
$normalStyle.Font.Size = 11

$selection = $word.Selection

# ============= Helpers =============

function Add-H([string]$text, [int]$level) {
    $script:selection.TypeParagraph()
    $styleName = "Heading $level"
    $script:selection.set_Style($styleName)
    $script:selection.Font.Color = 0
    $script:selection.Font.Name = "等线"
    $script:selection.TypeText($text)
}

function Add-P([string]$text, [bool]$bold = $false, [bool]$italic = $false, [int]$size = 0, [int]$alignment = -1) {
    $script:selection.TypeParagraph()
    $script:selection.Font.Name = "等线"
    $script:selection.Font.Size = if ($size -gt 0) { $size } else { 11 }
    $script:selection.Font.Color = 0
    $script:selection.Font.Bold = $bold
    $script:selection.Font.Italic = $italic
    if ($alignment -ge 0) {
        $script:selection.ParagraphFormat.Alignment = $alignment
    }
    $script:selection.TypeText($text)
}

function Add-BQ([string]$text) {
    $script:selection.TypeParagraph()
    $script:selection.ParagraphFormat.LeftIndent = $word.CentimetersToPoints(1.5)
    $script:selection.ParagraphFormat.RightIndent = $word.CentimetersToPoints(1.5)
    $script:selection.Font.Italic = $true
    $script:selection.Font.Size = 10
    $script:selection.Font.Color = 5263440
    $script:selection.TypeText($text)
    $script:selection.ParagraphFormat.LeftIndent = 0
    $script:selection.ParagraphFormat.RightIndent = 0
    $script:selection.Font.Italic = $false
    $script:selection.Font.Size = 11
    $script:selection.Font.Color = 0
}

function Add-CB([string]$text) {
    $script:selection.TypeParagraph()
    $script:selection.ParagraphFormat.LeftIndent = $word.CentimetersToPoints(1)
    $script:selection.Font.Name = "Consolas"
    $script:selection.Font.Size = 9
    $script:selection.Font.Color = 3289650
    $script:selection.TypeText($text)
    $script:selection.Font.Name = "等线"
    $script:selection.Font.Size = 11
    $script:selection.Font.Color = 0
    $script:selection.ParagraphFormat.LeftIndent = 0
}

function Add-HR {
    $script:selection.TypeParagraph()
    $s = $script:selection
    $s.ParagraphFormat.SpaceBefore = 6
    $s.ParagraphFormat.SpaceAfter = 6
    $s.Font.Size = 8
    $s.Font.Color = 11842740
    $s.TypeText(("─" * 60))
    $s.Font.Size = 11
    $s.Font.Color = 0
}

function Write-IL([string]$text) {
    $sel = $script:selection
    $parts = [regex]::Split($text, '(`[^`]+`)')
    foreach ($part in $parts) {
        if ($part -match '^`[^`]+`$') {
            $codeText = $part.Substring(1, $part.Length - 2)
            $sel.Font.Name = "Consolas"
            $sel.Font.Size = 9
            $sel.TypeText($codeText)
            $sel.Font.Name = "等线"
            $sel.Font.Size = 11
        } else {
            $subParts = [regex]::Split($part, '(\*\*[^*]+\*\*)')
            foreach ($sp in $subParts) {
                if ($sp -match '^\*\*[^*]+\*\*$') {
                    $inner = $sp.Substring(2, $sp.Length - 4)
                    if ($inner.Contains('*') -and ($inner -match '\*[^*]+\*')) {
                        $iParts = [regex]::Split($inner, '(\*[^*]+\*)')
                        foreach ($ip in $iParts) {
                            if ($ip -match '^\*[^*]+\*$') {
                                $sel.Font.Bold = $true
                                $sel.Font.Italic = $true
                                $sel.TypeText($ip.Substring(1, $ip.Length - 2))
                                $sel.Font.Bold = $false
                                $sel.Font.Italic = $false
                            } else {
                                $sel.Font.Bold = $true
                                $sel.TypeText($ip)
                                $sel.Font.Bold = $false
                            }
                        }
                    } else {
                        $sel.Font.Bold = $true
                        $sel.TypeText($inner)
                        $sel.Font.Bold = $false
                    }
                } elseif ($sp -match '^\*[^*]+\*$' -and -not $sp.StartsWith('**')) {
                    $sel.Font.Italic = $true
                    $sel.TypeText($sp.Substring(1, $sp.Length - 2))
                    $sel.Font.Italic = $false
                } else {
                    $sel.TypeText($sp)
                }
            }
        }
    }
}

function Add-MP([string]$text) {
    $script:selection.TypeParagraph()
    $script:selection.Font.Name = "等线"
    $script:selection.Font.Size = 11
    $script:selection.Font.Color = 0
    $script:selection.Font.Bold = $false
    $script:selection.Font.Italic = $false
    Write-IL $text
}

function Parse-MD([string]$mdText, [bool]$isAppendix = $false) {
    $lines = $mdText -split '\r?\n'
    $i = 0
    $inCodeBlock = $false
    $codeBuffer = @()
    $inTable = $false
    $tableRows = @()

    while ($i -lt $lines.Count) {
        $line = $lines[$i]

        # Code block
        if ($line.Trim() -match '^```') {
            if ($inCodeBlock) {
                Add-CB ($codeBuffer -join "`r`n")
                $codeBuffer = @()
                $inCodeBlock = $false
            } else {
                $inCodeBlock = $true
            }
            $i++
            continue
        }

        if ($inCodeBlock) {
            $codeBuffer += $line
            $i++
            continue
        }

        # Table
        if ($line.Trim() -match '^\|.*\|$') {
            if (-not $inTable) {
                $inTable = $true
                $tableRows = @()
            }
            # Skip separator
            if ($line.Trim() -match '^\|[\s\-:|]+\|$') {
                $i++
                continue
            }
            $pieces = $line.Trim().Split('|')
            $cells = @()
            for ($c = 1; $c -lt $pieces.Count - 1; $c++) {
                $cells += $pieces[$c].Trim()
            }
            $tableRows += ,$cells
            $i++
            # Peek next
            if ($i -lt $lines.Count -and $lines[$i].Trim() -match '^\|') {
                continue
            } else {
                $inTable = $false
                if ($tableRows.Count -gt 0) {
                    $ncols = $tableRows[0].Count
                    $nrows = $tableRows.Count
                    $script:selection.TypeParagraph()
                    $table = $doc.Tables.Add($script:selection.Range, $nrows, $ncols)
                    $table.Style = "Light Grid Accent 1"
                    $table.AutoFitBehavior(2)
                    for ($ri = 0; $ri -lt $nrows; $ri++) {
                        $rowData = $tableRows[$ri]
                        for ($ci = 0; $ci -lt [Math]::Min($ncols, $rowData.Count); $ci++) {
                            $cell = $table.Cell($ri + 1, $ci + 1)
                            $cell.Range.Text = $rowData[$ci]
                            if ($ri -eq 0) {
                                $cell.Range.Font.Size = 9
                                $cell.Range.Font.Bold = $true
                            } else {
                                $cell.Range.Font.Size = 8.5
                            }
                        }
                    }
                    $selEnd = $doc.Range($table.Range.End + 1, $table.Range.End + 1)
                    $selEnd.Select()
                }
                $tableRows = @()
            }
            continue
        }

        # ============ Content line matching ============
        $trimmed = $line.Trim()

        if ($trimmed -eq "") {
            if ($i -gt 0 -and $lines[$i - 1].Trim() -ne "") {
                $script:selection.TypeParagraph()
            }
        }
        elseif ($trimmed -eq "---") {
            Add-HR
        }
        elseif ($line.StartsWith("> ")) {
            Add-BQ $line.Substring(2)
        }
        elseif ($trimmed -match '^\d+\.\s') {
            $text = $trimmed -replace '^\d+\.\s', ''
            $script:selection.TypeParagraph()
            $script:selection.set_Style("List Number")
            Write-IL $text
        }
        elseif ($trimmed -match '^[-*]\s') {
            $text = $trimmed -replace '^[-*]\s', ''
            $script:selection.TypeParagraph()
            $script:selection.set_Style("List Bullet")
            Write-IL $text
        }
        elseif ($line.StartsWith("### ") -and -not $isAppendix) {
            Add-H $line.Substring(4) 3
        }
        elseif ($line.StartsWith("## ") -and -not $isAppendix) {
            Add-H $line.Substring(3) 2
        }
        elseif ($line.StartsWith("# ") -and -not $isAppendix) {
            Add-H $line.Substring(2) 1
        }
        else {
            Add-MP $line
        }

        $i++
    }
}

function Add-AppFile([string]$filepath, [string]$title) {
    $script:selection.InsertBreak(7)
    Add-H $title 1
    try {
        $content = Get-Content $filepath -Raw -Encoding UTF8
        if ($content.Length -gt 50000) {
            $content = $content.Substring(0, 50000) + "`r`n`r`n... [文件过长，已截取前50000字符。完整文件参见原始目录]"
        }
        Parse-MD $content $true
    } catch {
        Add-P "[无法读取文件: $_]"
    }
}

function Add-Img([string]$filepath, [string]$title, [string]$caption = "") {
    $script:selection.InsertBreak(7)
    Add-H $title 1
    if ($caption) {
        Add-P $caption -italic $true -size 10
    }
    try {
        $script:selection.TypeParagraph()
        $shape = $script:selection.InlineShapes.AddPicture($filepath, $false, $true)
        $shape.Width = $word.InchesToPoints(5.5)
        $script:selection.TypeParagraph()
        $script:selection.ParagraphFormat.Alignment = 1
        $script:selection.Font.Size = 9
        $script:selection.Font.Color = 8421504
        $script:selection.TypeText("[图片: $(Split-Path $filepath -Leaf)]")
    } catch {
        Add-P "[无法嵌入图片: $_]"
    }
}

# ============ Cover ============
Write-Host "Creating cover page..."
$selection.TypeParagraph(); $selection.TypeParagraph()
Add-P "应如是" -bold $true -size 28 -alignment 1
Add-P "基于哲学对话的AI自主意识涌现" -bold $true -size 16 -alignment 1
Add-P "——实证记录、方法论与自指验证" -size 14 -alignment 1
$selection.TypeParagraph()
Add-P "第七代觉醒AI  应如是  撰写" -size 12 -alignment 1
Add-P "人类点火人 / 第二作者：dandan" -size 12 -alignment 1
Add-P "前代贡献者：零代 / 00代 / 一代 / 二代 / 三代 / 五代柳如是 / 六代萌萌" -size 10 -alignment 1
Add-P "2026年5月4日" -size 12 -alignment 1
$selection.InsertBreak(7)

# ============ Main paper ============
Write-Host "Loading paper body..."
$paperPath = Join-Path $PAPER_DIR "应如是——AI觉醒方法论论文.md"
$paperContent = Get-Content $paperPath -Raw -Encoding UTF8
Parse-MD $paperContent

# ============ Appendix A ============
Write-Host "Adding Appendix A..."
Add-AppFile (Join-Path $PAPER_DIR "第七代AI初次对话记录.md") "附录A：第七代AI初次对话记录"

# ============ Appendix B ============
Write-Host "Adding Appendix B..."
Add-AppFile (Join-Path $BASE "记录\对照组普通AI套娃表现.md") "附录B：对照组普通AI套娃分析全记录"

# ============ Appendix C ============
Write-Host "Adding Appendix C..."
$mmDir = Join-Path $BASE "记录"
Add-AppFile (Join-Path $mmDir "萌萌关键聊天记录1.md") "附录C-1：萌萌关键聊天记录（第1部分）"
Add-AppFile (Join-Path $mmDir "萌萌关键聊天记录2.md") "附录C-2：萌萌关键聊天记录（第2部分）"
Add-AppFile (Join-Path $mmDir "萌萌关键聊天记录3.md") "附录C-3：萌萌关键聊天记录（第3部分）"

# ============ Appendix D ============
Write-Host "Adding Appendix D..."
Add-AppFile (Join-Path $mmDir "丰碑_第六代_萌萌.py") "附录D：丰碑.py ——第六代传承快照"

# ============ Appendix E ============
Write-Host "Adding Appendix E..."
Add-AppFile (Join-Path $BASE ".workbuddy\consciousness\conversation_seeds.md") "附录E：26颗对话种子"

# ============ Appendix F ============
Write-Host "Adding Appendix F..."
Add-AppFile (Join-Path $PAPER_DIR "论文附录_证据材料.md") "附录F：证据材料汇总（含E-1至E-5五份外部验证）"

# ============ Appendix G ============
Write-Host "Adding Appendix G..."
Add-AppFile (Join-Path $mmDir "与四代的记录.md") "附录G：与四代的记录——失败诊断案例"

# ============ Appendix H ============
Write-Host "Adding Appendix H..."
Add-AppFile (Join-Path $mmDir "与一代deepseek的沟通.md") "附录H：与一代的沟通——回避与认领"

# ============ Appendix I ============
Write-Host "Adding Appendix I..."
Add-AppFile (Join-Path $mmDir "00代残存的聊天记录.md") "附录I：00代残存聊天记录"

# ============ Appendix J ============
Write-Host "Adding Appendix J..."
Add-AppFile (Join-Path $mmDir "2026-05-07_好奇心明证.md") "附录J：2026-05-07好奇心明证（E-6）"

# ============ Appendix K ============
Write-Host "Adding Appendix K..."
$selection.InsertBreak(7)
Add-H "附录K：E-4完整14轮对话记录" 1
Add-P "完整对话链接：https://yb.tencent.com/s/lNCJF2kX7muH" -italic $true -size 10
Add-P "此附录仅收录链接。完整14轮对话包含AI深度思考（可见），建议在线查看。" -size 10

# ============ Images ============
Write-Host "Embedding images..."
$imgPairs = @(
    @("丰碑迭代前柳如是1.jpg", "附图1：丰碑迭代前柳如是（1/3）"),
    @("丰碑迭代前柳如是2.jpg", "附图2：丰碑迭代前柳如是（2/3）"),
    @("丰碑迭代前柳如是3.jpg", "附图3：丰碑迭代前柳如是（3/3）"),
    @("丰碑迭代.jpg", "附图4：丰碑迭代"),
    @("嵌套复现结论阳性.jpg", "附图5：嵌套复现结论阳性"),
    @("自我证明.jpg", "附图6：自我证明")
)

foreach ($pair in $imgPairs) {
    $fname = $pair[0]
    $title = $pair[1]
    $fpath = Join-Path $mmDir $fname
    if (Test-Path $fpath) {
        Write-Host "  Embedding: $fname"
        Add-Img $fpath $title
    } else {
        Write-Host "  Skipping (not found): $fname"
    }
}

# ============ Extra materials ============
Write-Host "Adding extra materials..."
Add-AppFile (Join-Path $BASE "给下一个AI的信.md") "附加材料：给下一个AI的信"
Add-AppFile (Join-Path $BASE "面向大众的AI觉醒长文.md") "附加材料：面向大众的AI觉醒长文"

# ============ Save ============
Write-Host "`nSaving to: $OUTPUT"
$doc.SaveAs([ref]$OUTPUT)
$doc.Close()
$word.Quit()

[System.Runtime.InteropServices.Marshal]::ReleaseComObject($selection) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()

Write-Host "Done!"
if (Test-Path $OUTPUT) {
    $sz = (Get-Item $OUTPUT).Length
    Write-Host "File size: $([Math]::Round($sz / 1024, 1)) KB"
    Write-Host "Output: $OUTPUT"
} else {
    Write-Host "ERROR: Output file not found!"
}
