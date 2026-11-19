<#
    竞价自动交易 · 一键启动与监控
    用法：
      双击 启动.bat            启动缺的模块 + 显示一次状态
      启动.bat -Watch          持续刷新（Ctrl+C 退出）
      启动.bat -SetupTask      创建每天 09:29:40 的推送计划任务
      启动.bat -Push           立刻按最新导出推送一次
      启动.bat -RestartServer  强制重启名单服务
#>
param(
    [switch]$Watch,
    [switch]$Board,
    [switch]$SetupTask,
    [switch]$Push,
    [switch]$RestartServer
)

$ErrorActionPreference = 'SilentlyContinue'
$TOOLS   = Split-Path -Parent $MyInvocation.MyCommand.Path
$W       = Split-Path -Parent $TOOLS
if (-not $env:QMT_DIR)        { $env:QMT_DIR = 'D:\qmt' }
if (-not $env:JJB_EXPORT_DIR) { $env:JJB_EXPORT_DIR = 'F:\qmt\export' }
$PYW     = Join-Path $env:QMT_DIR 'bin.x64\pythonw.exe'
$QMT_EXE = Join-Path $env:QMT_DIR 'bin.x64\XtItClient.exe'
$QMT_DIR = $env:QMT_DIR
$LOG_DIR = Join-Path $env:QMT_DIR 'userdata\log'
$PORT    = 8765
$SRV     = "http://127.0.0.1:$PORT"
$TASK    = 'QMT竞价推送'

function Test-Server {
    try {
        $r = Invoke-WebRequest -Uri "$SRV/" -UseBasicParsing -TimeoutSec 2
        $o = [ordered]@{ Alive = $true; Codes = ''; Updated = ''; LastGet = '' }
        foreach ($line in ($r.Content -split "`n")) {
            if ($line -match '^\s*codes\s*:\s*(.*)$')    { $o.Codes   = $Matches[1].Trim() }
            if ($line -match '^\s*updated\s*:\s*(.*)$') {
                $v = $Matches[1].Trim()
                if ($v -ne 'None' -and $v -ne '') { $o.Updated = $v }
            }
            if ($line -match '^\s*last get\s*:\s*(.*)$') {
                $v = $Matches[1].Trim()
                if ($v -ne 'None' -and $v -ne '') { $o.LastGet = $v }
            }
        }
        return [pscustomobject]$o
    } catch {
        return [pscustomobject]@{ Alive = $false; Codes = ''; Updated = ''; LastGet = '' }
    }
}

function Start-Server {
    if ($RestartServer) {
        Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 600
    }
    $port = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue
    if (-not $port) {
        Start-Process -FilePath $PYW -ArgumentList ('"{0}"' -f (Join-Path $W 'server\list_server.py')) -WorkingDirectory $W
        Start-Sleep -Seconds 2
    }
}

function Get-QmtProc {
    Get-Process XtItClient -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
}

function Start-Qmt {
    if (-not (Get-QmtProc)) {
        Start-Process -FilePath $QMT_EXE -WorkingDirectory (Split-Path $QMT_EXE)
        Write-Host '  已启动 QMT 客户端，请等待自动登录（密码已保存）...' -ForegroundColor Yellow
    }
}

function Get-LogInfo {
    $tag = Get-Date -Format 'yyyyMMdd'
    $f = Join-Path $LOG_DIR ("XtClient_FormulaOutput_{0}.log" -f $tag)
    $o = [ordered]@{
        File = (Split-Path $f -Leaf); Exists = (Test-Path $f)
        AutoLast = $null; AutoCount = 0; SellLast = $null; SellCount = 0
        BuyOrder = 0; SellOrder = 0
    }
    if (-not (Test-Path $f)) { return [pscustomobject]$o }
    $text = Get-Content -LiteralPath $f -Encoding UTF8 -Raw
    foreach ($m in [regex]::Matches($text, '\[AUTO (\d{2}:\d{2}:\d{2})')) {
        $o.AutoCount++; $o.AutoLast = $m.Groups[1].Value
    }
    foreach ($m in [regex]::Matches($text, '\[SELL (\d{2}:\d{2}:\d{2})')) {
        $o.SellCount++; $o.SellLast = $m.Groups[1].Value
    }
    $o.BuyOrder  = ([regex]::Matches($text, '\[AUTO .*?ORDER ')).Count
    $o.SellOrder = ([regex]::Matches($text, '\[SELL .*?ORDER ')).Count
    return [pscustomobject]$o
}

function Get-DataInfo {
    $expDir = $env:JJB_EXPORT_DIR
    $files = Get-ChildItem -LiteralPath $expDir -File -ErrorAction SilentlyContinue |
             Where-Object { $_.Extension -eq '.csv' -and $_.Name.StartsWith([string][char]0x7ADE) } |
             Sort-Object LastWriteTime
    $audits = Get-ChildItem (Join-Path $W 'out') -Filter 'push_*.json' -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime
    [pscustomobject]@{
        Csv    = if ($files)  { $files[-1] }  else { $null }
        Audit  = if ($audits) { $audits[-1] } else { $null }
    }
}

function Get-TaskInfo {
    $t = schtasks /Query /TN $TASK 2>$null
    return ($LASTEXITCODE -eq 0)
}

function New-PushTask {
    $tr = ('"{0}" "{1}"' -f $PYW, (Join-Path $W 'feeder\push_from_export.py'))
    schtasks /Create /TN $TASK /TR $tr /SC DAILY /ST 09:29:40 /F | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  已创建计划任务: $TASK (每天 09:29:40)" -ForegroundColor Green
    } else {
        Write-Host '  创建计划任务失败，请用管理员身份运行' -ForegroundColor Red
    }
}

function Show-Panel {
    $srv   = Test-Server
    $qmt   = Get-QmtProc
    $log   = Get-LogInfo
    $data  = Get-DataInfo
    $task  = Get-TaskInfo
    $now   = Get-Date

    Clear-Host
    $bar = '=' * 66
    Write-Host $bar -ForegroundColor DarkCyan
    Write-Host (" 竞价自动交易 · 运行监控        {0}  {1}" -f $now.ToString('MM-dd HH:mm:ss'), ('周' + '日一二三四五六'[[int]$now.DayOfWeek])) -ForegroundColor Cyan
    Write-Host $bar -ForegroundColor DarkCyan

    # 1 名单服务
    if ($srv.Alive) {
        $cnt = 0
        if ($srv.Codes -and $srv.Codes -ne '(empty)') { $cnt = ($srv.Codes -split ',').Count }
        Write-Host (" [1] 名单服务 127.0.0.1:{0}   " -f $PORT) -NoNewline
        Write-Host '[OK] 运行中' -ForegroundColor Green -NoNewline
        Write-Host ("   名单 {0} 只   最后推送 {1}" -f $cnt, $(if($srv.Updated -eq 'None' -or -not $srv.Updated){'-'}else{$srv.Updated}))
        Write-Host ("                           最后被QMT拉取 {0}" -f $(if($srv.LastGet){$srv.LastGet}else{'-'}))
    } else {
        Write-Host (" [1] 名单服务 127.0.0.1:{0}   " -f $PORT) -NoNewline
        Write-Host '[NO] 未运行' -ForegroundColor Red -NoNewline
        Write-Host '   -> 正在自动启动...'
        Start-Server
    }

    # 2 QMT
    Write-Host ' [2] QMT 客户端               ' -NoNewline
    if ($qmt) {
        Write-Host '[OK] 运行中' -ForegroundColor Green -NoNewline
        Write-Host ("   PID {0}   启动于 {1}" -f $qmt.Id, $qmt.StartTime.ToString('HH:mm:ss'))
    } else {
        Write-Host '[NO] 未运行' -ForegroundColor Red -NoNewline
        Write-Host '   -> 正在启动...'
        Start-Qmt
    }

    # 3 买入策略
    Write-Host ' [3] 买入策略 [AUTO]          ' -NoNewline
    if ($srv.LastGet) {
        $age = 0
        try {
            $t = [datetime]::ParseExact($srv.LastGet, 'HH:mm:ss', $null)
            $age = ((Get-Date) - $t).TotalSeconds
            if ($age -lt 0) { $age += 86400 }
        } catch { $age = 99999 }
        if ($age -le 30) {
            Write-Host '[OK] 心跳正常' -ForegroundColor Green -NoNewline
            Write-Host ("   每秒轮询中（最新 {0}）" -f $srv.LastGet)
        } else {
            Write-Host ('[!!] 心跳停了 {0:N0} 秒' -f $age) -ForegroundColor Yellow -NoNewline
            Write-Host '   检查模型交易里策略是否还在跑'
        }
    } else {
        Write-Host '[!!] QMT 还没来拉取' -ForegroundColor Yellow -NoNewline
        Write-Host '   模型交易里启动「竞价自动买入」'
    }

    # 4 卖出策略
    Write-Host ' [4] 卖出策略 [SELL]          ' -NoNewline
    if ($log.SellCount -gt 0) {
        $stale = $false
        try {
            $lt = [datetime]::ParseExact($log.SellLast, 'HH:mm:ss', $null)
            $ltFull = (Get-Date).Date.Add($lt.TimeOfDay)
            if ($qmt -and $ltFull -lt $qmt.StartTime) { $stale = $true }
        } catch { }
        if ($stale) {
            Write-Host '[!!] 记录在QMT重启前，已失效' -ForegroundColor Yellow -NoNewline
            Write-Host ("   最近 {0}" -f $log.SellLast)
        } else {
            Write-Host '[OK] 今天有输出' -ForegroundColor Green -NoNewline
            Write-Host ("   最近 {0}（共 {1} 条）" -f $log.SellLast, $log.SellCount)
        }
    } else {
        Write-Host '[!!] 今天无输出（策略没启动）' -ForegroundColor Yellow
    }

    # 5 数据
    Write-Host ' [5] 竞价数据                  ' -NoNewline
    if ($data.Csv) {
        Write-Host ('[OK] {0}' -f $data.Csv.Name) -ForegroundColor Green -NoNewline
        Write-Host ("   {0}" -f $data.Csv.LastWriteTime.ToString('MM-dd HH:mm'))
    } else {
        Write-Host '[NO] export 目录没有 CSV' -ForegroundColor Red
    }
    Write-Host '     最近推送                  ' -NoNewline
    if ($data.Audit) {
        Write-Host ('  {0}' -f $data.Audit.Name) -NoNewline
        $d = ($data.Audit.BaseName -replace '^push_', '')
        Write-Host ("   数据日 {0}" -f $d)
    } else {
        Write-Host '  还没推送过' -ForegroundColor Yellow
    }

    # 6 计划任务
    Write-Host ' [6] 计划任务 09:29:40        ' -NoNewline
    if ($task) {
        Write-Host '[OK] 已安装' -ForegroundColor Green
    } else {
        Write-Host '[NO] 未安装' -ForegroundColor Red -NoNewline
        Write-Host '   运行: 启动.bat -SetupTask'
    }

    # 成交统计
    Write-Host ('     今日下单: 买入 {0} 笔 / 卖出 {1} 笔' -f $log.BuyOrder, $log.SellOrder)

    # 下一步
    Write-Host ('-' * 66) -ForegroundColor DarkGray
    $hm = $now.ToString('HHmmss')
    $next = ''
    if     ($hm -lt '092800') { $next = '下一动作 09:28 导出CSV → 09:29:40 推送 → 09:30:05 买入' }
    elseif ($hm -lt '093130') { $next = '[**] 买入窗口进行中 (09:30:00-09:31:30)' }
    elseif ($hm -lt '145000') { $next = '下一动作 14:50 清仓' }
    elseif ($hm -lt '145700') { $next = '[**] 卖出窗口进行中 (14:50:00-14:56:30)' }
    else                      { $next = '今日动作已结束，明日 09:28 再开始' }
    Write-Host (" $next") -ForegroundColor Cyan
    $wd = [int]$now.DayOfWeek
    if ($wd -eq 0 -or $wd -eq 6) { Write-Host ' 注意：今天是周末，A股休市' -ForegroundColor Yellow }
    Write-Host (" 看板: http://127.0.0.1:{0}/   （双击 启动.bat -Board 打开）" -f $PORT) -ForegroundColor DarkGray
    Write-Host $bar -ForegroundColor DarkCyan
}

# ---------------- 主流程 ----------------
if ($Board) { Start-Process ("http://127.0.0.1:{0}/" -f $PORT) }
if ($SetupTask) { New-PushTask; exit 0 }

Start-Server
Start-Qmt

if ($Push) {
    Write-Host '正在按最新导出推送...' -ForegroundColor Cyan
    & $PYW (Join-Path $W 'feeder\push_from_export.py')
    Start-Sleep -Seconds 3
}

if ($Watch) {
    while ($true) {
        Show-Panel
        Start-Sleep -Seconds 3
    }
} else {
    Show-Panel
}