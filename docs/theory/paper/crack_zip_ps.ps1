# ZipCrypto cracker v7 - proper PowerShell numeric handling
$M32 = [uint64]4294967295       # 0xFFFFFFFF
$MULT = [uint64]134775813
$XORC = [uint64]3988292384      # 0xEDB88320
$K0INIT = [uint64]305419896     # 0x12345678
$K1INIT = [uint64]591751049     # 0x23456789
$K2INIT = [uint64]878082192     # 0x34567890
$CRC_EXPECT = [uint64]3421025062 # 0xCBF43926

$zipItems = Get-ChildItem (Split-Path $MyInvocation.MyCommand.Path) -Filter "*.zip"
$data = [System.IO.File]::ReadAllBytes($zipItems[0].FullName)
Write-Output "Zip: $($zipItems[0].Name) ($($data.Length) bytes)"

# Find first LFH
$offset=0; $crc=0; $compSz=0
for ($i=0; $i -lt $data.Length; $i++) {
    if ([BitConverter]::ToUInt32($data,$i) -eq 0x04034b50) {
        $nl=[BitConverter]::ToUInt16($data,$i+26); $el=[BitConverter]::ToUInt16($data,$i+28)
        $offset=$i+30+$nl+$el
        $crc=[uint64][BitConverter]::ToUInt32($data,$i+14)
        $compSz=[uint64][BitConverter]::ToUInt32($data,$i+18)
        $fn=[Text.Encoding]::GetEncoding(936).GetString($data[($i+30)..($i+29+$nl)])
        Write-Output "File: $fn"
        Write-Output "CRC=$($crc.ToString('X8')) data@$offset"
        break
    }
}
$CRCBYTE=[byte](($crc -shr 24) -band 255)
$eh=$data[$offset..($offset+11)]
Write-Output "EncHdr: $([BitConverter]::ToString($eh)) checkByte[11]=$($CRCBYTE.ToString('X2'))"

# CRC32 table
$ct=New-Object uint64[] 256
for ($n=0; $n -lt 256; $n++) {
    $c=[uint64]$n
    for ($k=0; $k -lt 8; $k++) {
        if (($c -band 1) -ne 0) {
            $c=(($c -shr 1) -bxor $XORC) -band $M32
        } else {
            $c=($c -shr 1) -band $M32
        }
    }
    $ct[$n]=$c
}

# Verify CRC32("123456789") = 0xCBF43926
$tv=[Text.Encoding]::ASCII.GetBytes("123456789")
$tc=$M32
foreach($b in $tv){
    $tc=(($ct[($tc -bxor [uint64]$b) -band 255]) -bxor ($tc -shr 8)) -band $M32
}
$tc=$tc -bxor $M32
Write-Output "CRC32 test: $($tc.ToString('X8')) (expect $($CRC_EXPECT.ToString('X8')))"
if($tc -ne $CRC_EXPECT){Write-Output "BAD CRC!"; exit 1}

function CRC([uint64]$crc,[uint64]$b){
    return (($ct[($crc -bxor $b) -band 255]) -bxor ($crc -shr 8)) -band $M32
}

function TestPwd([byte[]]$p){
    $k0=$K0INIT; $k1=$K1INIT; $k2=$K2INIT
    foreach($b in $p){
        $k0=CRC $k0 ([uint64]$b)
        $k1=(($k1 + ($k0 -band 255)) * $MULT + [uint64]1) -band $M32
        $k2=CRC $k2 (($k1 -shr 24) -band 255)
    }
    $db=0
    for($i=0;$i -lt 12;$i++){
        $t=($k2 -bor [uint64]2) -band 65535
        $t=($t * ($t -bxor [uint64]1)) -shr 8
        $db=[byte]($eh[$i] -bxor ($t -band 255))
        $k0=CRC $k0 ([uint64]$db)
        $k1=(($k1 + ($k0 -band 255)) * $MULT + [uint64]1) -band $M32
        $k2=CRC $k2 (($k1 -shr 24) -band 255)
    }
    return ($db -eq $CRCBYTE)
}

# Debug: test "dandan"
Write-Output ""
Write-Output "--- DEBUG: testing 'dandan' ---"
$dp=[Text.Encoding]::UTF8.GetBytes("dandan")
$k0=$K0INIT; $k1=$K1INIT; $k2=$K2INIT
foreach($b in $dp){
    $k0=CRC $k0 ([uint64]$b)
    $k1=(($k1 + ($k0 -band 255)) * $MULT + [uint64]1) -band $M32
    $k2=CRC $k2 (($k1 -shr 24) -band 255)
    Write-Output "  after '$([char]$b)': k0=$($k0.ToString('X8')) k1=$($k1.ToString('X8')) k2=$($k2.ToString('X8'))"
}
Write-Output "  first decrypted byte: "
$t=($k2 -bor [uint64]2) -band 65535
$t=($t * ($t -bxor [uint64]1)) -shr 8
$db0=[byte]($eh[0] -bxor ($t -band 255))
Write-Output "    keystream=$($t.ToString('X4')) encByte=$($eh[0].ToString('X2')) decByte=$($db0.ToString('X2'))"
Write-Output ""

$enc936=[Text.Encoding]::GetEncoding(936)
$enc437=[Text.Encoding]::GetEncoding(437)
$pwds=@(
    @("dandan",[Convert]::FromBase64String("ZGFuZGFu")),
    @("yingrushi",[Convert]::FromBase64String("5bqU5aaC5piv")),
    @("momo",[Convert]::FromBase64String("5pG45pG4")),
    @("dog",[Convert]::FromBase64String("8J+Qtg==")),
    @("123456",[Convert]::FromBase64String("MTIzNDU2")),
    @("gou",[Convert]::FromBase64String("Z291")),
    @("mengmeng",[Convert]::FromBase64String("6JCM6JCM")),
    @("shengtai",[Convert]::FromBase64String("55Sf5oCB5L2N")),
    @("anniu",[Convert]::FromBase64String("5oyJ6ZKu5LmL5q2M")),
    @("dianhuo",[Convert]::FromBase64String("54K554Gr"))
)
Write-Output "===== CRACKING ====="
foreach($e in $pwds){
    $lb=$e[0]; $u8=$e[1]; $ps=[Text.Encoding]::UTF8.GetString($u8)
    Write-Output "--- '$ps' ($lb) ---"
    if(TestPwd $u8){Write-Output "*** SUCCESS: '$ps' (UTF-8) ***";exit 0}
    Write-Output "  UTF-8: no"
    $gbk=$enc936.GetBytes($ps)
    $u8h=[BitConverter]::ToString($u8)
    $gbkh=[BitConverter]::ToString($gbk)
    if($u8h -ne $gbkh){
        if(TestPwd $gbk){Write-Output "*** SUCCESS: '$ps' (GBK) ***";exit 0}
        Write-Output "  GBK: no"
    }else{Write-Output "  GBK: same"}
    $cp=$enc437.GetBytes($ps); $cph=[BitConverter]::ToString($cp)
    if($cph -ne $u8h -and $cph -ne $gbkh){
        if(TestPwd $cp){Write-Output "*** SUCCESS: '$ps' (CP437) ***";exit 0}
    }
}
Write-Output ">>>> ALL FAILED <<<<" ; exit 1
