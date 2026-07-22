# PowerShell script to crack ZipCrypto encrypted zip using C# Add-Type
$zipPath = "c:\Users\dandan\Desktop\小说\应如是论文\应如是——AI觉醒方法论论文.zip"
$targetFile = "应如是——AI觉醒方法论论文.md"
$expectedSize = 67102

# Passwords to try
$passwords = @(
    "dandan",
    "应如是",
    "摸摸",
    "🐶",
    "123456",
    "gou",
    "萌萌",
    "生态位",
    "按钮之歌",
    "点火"
)

# Compile C# ZipCrypto implementation
$csharpCode = @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public class ZipCryptoCracker
{
    private static uint[] crcTable;

    static ZipCryptoCracker()
    {
        crcTable = new uint[256];
        for (uint i = 0; i < 256; i++)
        {
            uint crc = i;
            for (int j = 0; j < 8; j++)
            {
                if ((crc & 1) != 0)
                    crc = (crc >> 1) ^ 0xEDB88320;
                else
                    crc >>= 1;
            }
            crcTable[i] = crc;
        }
    }

    private static uint CRC32(uint oldCrc, byte b)
    {
        return crcTable[(oldCrc ^ b) & 0xFF] ^ (oldCrc >> 8);
    }

    private uint key0, key1, key2;

    public ZipCryptoCracker()
    {
        key0 = 0x12345678;
        key1 = 0x23456789;
        key2 = 0x34567890;
    }

    private void UpdateKeys(byte b)
    {
        key0 = CRC32(key0, b);
        key1 = (key1 + (key0 & 0xFF)) * 134775813 + 1;
        key2 = CRC32(key2, (byte)(key1 >> 24));
    }

    private byte DecryptByte()
    {
        ushort temp = (ushort)(key2 | 2);
        temp = (ushort)((temp * (temp ^ 1)) >> 8);
        return (byte)temp;
    }

    public void Init(byte[] password)
    {
        foreach (byte b in password)
            UpdateKeys(b);
    }

    public byte Decrypt(byte encrypted)
    {
        byte plain = (byte)(encrypted ^ DecryptByte());
        UpdateKeys(plain);
        return plain;
    }
}

public class ZipCryptoReader
{
    public static byte[] TryDecrypt(byte[] zipData, string targetFileName, string password, Encoding encoding)
    {
        try
        {
            byte[] pwdBytes = encoding.GetBytes(password);
            
            // Find local file header for target file
            // Local file header signature: 0x04034b50
            byte[] fileNameBytes = encoding.GetBytes(targetFileName);
            byte[] fileNameUtf8 = Encoding.UTF8.GetBytes(targetFileName);
            
            int pos = FindFileName(zipData, fileNameBytes);
            if (pos < 0) pos = FindFileName(zipData, fileNameUtf8);
            if (pos < 0) return null;
            
            // pos is now at the start of file name in local header
            // Local header structure:
            // 4 bytes: signature (0x04034b50)
            // 2 bytes: version needed
            // 2 bytes: general purpose bit flag
            // 2 bytes: compression method
            // 2 bytes: last mod file time
            // 2 bytes: last mod file date
            // 4 bytes: CRC-32
            // 4 bytes: compressed size
            // 4 bytes: uncompressed size
            // 2 bytes: file name length
            // 2 bytes: extra field length
            
            int headerStart = pos - 26; // filename starts 26 bytes into local header
            if (headerStart < 0) return null;
            
            // Verify signature
            if (BitConverter.ToUInt32(zipData, headerStart) != 0x04034b50) return null;
            
            ushort nameLen = BitConverter.ToUInt16(zipData, headerStart + 26);
            ushort extraLen = BitConverter.ToUInt16(zipData, headerStart + 28);
            int dataStart = headerStart + 30 + nameLen + extraLen;
            
            // Encrypted data starts here (12 bytes encryption header + compressed data)
            if (dataStart + 12 > zipData.Length) return null;
            
            // Read 12-byte encryption header
            // Bytes 0-9: random (last byte of this is used to verify password in traditional PKWARE)
            // Bytes 10-11: should match CRC/time upper byte when password is correct (PKWARE traditional)
            byte[] encHeader = new byte[12];
            Array.Copy(zipData, dataStart, encHeader, 0, 12);
            
            // Try to decrypt with password
            ZipCryptoCracker cracker = new ZipCryptoCracker();
            cracker.Init(pwdBytes);
            
            byte[] decrypted = new byte[12];
            for (int i = 0; i < 12; i++)
                decrypted[i] = cracker.Decrypt(encHeader[i]);
            
            // Check if password is correct
            // For traditional PKWARE encryption, byte 11 of decrypted header
            // should match the high byte of CRC-32 from the local header
            // But this check is not 100% reliable (1/256 false positive for single check)
            
            // Get the CRC from local header
            uint crc = BitConverter.ToUInt32(zipData, headerStart + 14);
            byte crcHigh = (byte)(crc >> 24);
            
            // Check byte 11 of decrypted data
            if (decrypted.Length >= 12)
            {
                // For store method (no compression), byte 11 should match CRC high byte
                // Let's check multiple aspects
                if (decrypted[11] == crcHigh)
                {
                    // Very likely correct password!
                    // Let's try to decrypt more to verify
                    uint compSize = BitConverter.ToUInt32(zipData, headerStart + 18);
                    if (compSize > 12 && dataStart + (int)compSize <= zipData.Length)
                    {
                        // Decrypt a chunk to verify
                        cracker = new ZipCryptoCracker();
                        cracker.Init(pwdBytes);
                        
                        // Decrypt encryption header
                        for (int i = 0; i < 12; i++)
                            cracker.Decrypt(encHeader[i]);
                        
                        // Decrypt some data
                        int toRead = Math.Min(200, (int)compSize - 12);
                        byte[] result = new byte[toRead];
                        for (int i = 0; i < toRead; i++)
                            result[i] = cracker.Decrypt(zipData[dataStart + 12 + i]);
                        
                        return result;
                    }
                }
            }
        }
        catch { }
        return null;
    }
    
    public static bool TryPassword(byte[] zipData, string targetFileName, string password)
    {
        byte[] result = null;
        
        // Try UTF-8
        result = TryDecrypt(zipData, targetFileName, password, Encoding.UTF8);
        if (result != null && IsValidText(result))
            return true;
        
        // Try CP437
        result = TryDecrypt(zipData, targetFileName, password, Encoding.GetEncoding(437));
        if (result != null && IsValidText(result))
            return true;
        
        // Try GBK  
        result = TryDecrypt(zipData, targetFileName, password, Encoding.GetEncoding(936));
        if (result != null && IsValidText(result))
            return true;
        
        return false;
    }
    
    private static bool IsValidText(byte[] data)
    {
        // Check if data looks like valid text
        if (data == null || data.Length < 3) return false;
        int printable = 0;
        foreach (byte b in data)
        {
            if (b >= 0x20 && b <= 0x7E) printable++;
            else if (b >= 0x80) printable++; // Allow UTF-8 continuation bytes
            else if (b == 0x0A || b == 0x0D || b == 0x09) printable++;
        }
        return printable > data.Length * 0.8;
    }
    
    private static int FindFileName(byte[] data, byte[] name)
    {
        for (int i = 0; i < data.Length - name.Length; i++)
        {
            bool match = true;
            for (int j = 0; j < name.Length; j++)
            {
                if (data[i + j] != name[j])
                {
                    match = false;
                    break;
                }
            }
            if (match) return i;
        }
        return -1;
    }
}
'@

Write-Host "Compiling C# ZipCrypto implementation..."
Add-Type -TypeDefinition $csharpCode -Language CSharp -ReferencedAssemblies "System.IO"
Write-Host "Compiled successfully."

# Read zip file
Write-Host "Reading zip file: $zipPath"
$zipBytes = [System.IO.File]::ReadAllBytes($zipPath)
Write-Host "Zip file size: $($zipBytes.Length) bytes"

Write-Host ""
Write-Host "Trying passwords..."
foreach ($pwd in $passwords) {
    Write-Host "  Trying: $pwd"
    $result = [ZipCryptoReader]::TryPassword($zipBytes, $targetFile, $pwd)
    if ($result) {
        Write-Host ""
        Write-Host "*** SUCCESS! Password is: $pwd ***" -ForegroundColor Green
        Write-Host "First bytes decoded:"
        $text = [System.Text.Encoding]::UTF8.GetString($result)
        Write-Host $text
        break
    } else {
        Write-Host "    FAILED"
    }
}
