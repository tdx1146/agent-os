import zipfile
import sys
import os
import struct

ZIP_PATH = r"c:\Users\dandan\Desktop\小说\应如是论文\应如是——AI觉醒方法论论文.zip"
TARGET_FILE = "应如是——AI觉醒方法论论文.md"
EXPECTED_SIZE = 67102

# Step 1 passwords (try in order)
PASSWORDS = [
    "dandan",
    "应如是",
    "摸摸",
    "🐶",
    "123456",
    "gou",
    "萌萌",
    "生态位",
    "按钮之歌",
    "点火",
]

def try_password(zf, pwd_str):
    """Try a password against the zip file."""
    try:
        pwd_bytes = pwd_str.encode('utf-8', errors='replace')
        # Some zip implementations use cp437 or utf-8 for legacy encryption
        zf.setpassword(pwd_bytes)
        # Try to read a small portion to verify password
        with zf.open(TARGET_FILE, 'r') as f:
            data = f.read(100)
        return True, data
    except Exception as e:
        return False, None

def try_password_cp437(zf, pwd_str):
    """Try password with cp437 encoding."""
    try:
        pwd_bytes = pwd_str.encode('cp437', errors='replace')
        zf.setpassword(pwd_bytes)
        with zf.open(TARGET_FILE, 'r') as f:
            data = f.read(100)
        return True, data
    except Exception as e:
        return False, None

def try_password_gbk(zf, pwd_str):
    """Try password with gbk encoding."""
    try:
        pwd_bytes = pwd_str.encode('gbk', errors='replace')
        zf.setpassword(pwd_bytes)
        with zf.open(TARGET_FILE, 'r') as f:
            data = f.read(100)
        return True, data
    except Exception as e:
        return False, None

def main():
    print("=" * 60)
    print("ZIP Password Cracker - Step 1: Dictionary Attack")
    print("=" * 60)
    print(f"Target: {ZIP_PATH}")
    print(f"File inside: {TARGET_FILE} ({EXPECTED_SIZE} bytes)")
    print()

    # Verify zip file exists
    if not os.path.exists(ZIP_PATH):
        print(f"ERROR: Zip file not found at {ZIP_PATH}")
        return

    # Check zip file
    try:
        zf = zipfile.ZipFile(ZIP_PATH, 'r')
        info_list = zf.infolist()
        print("Files in zip:")
        for info in info_list:
            print(f"  {info.filename} ({info.file_size} bytes, compress_type={info.compress_type})")
            # Check if it's ZipCrypto (compress_type 0 can still be encrypted)
            print(f"    Flag bits: {info.flag_bits:#06x}")
            # Bit 0 of flag_bits indicates encryption
            if info.flag_bits & 0x1:
                print(f"    ENCRYPTED: Yes (ZipCrypto or AES)")
    except Exception as e:
        print(f"ERROR opening zip: {e}")
        return

    # Try each password with multiple encodings
    found = False
    for pwd in PASSWORDS:
        print(f"Trying password: {pwd!r}")

        # Re-open zip for each attempt to reset state
        zf = zipfile.ZipFile(ZIP_PATH, 'r')
        success, data = try_password(zf, pwd)
        zf.close()

        if success:
            print(f"\n*** SUCCESS! Password found: {pwd!r} (UTF-8 encoding) ***")
            print(f"First 100 bytes: {data[:100]}")
            found = True
            break

        # Try cp437
        zf = zipfile.ZipFile(ZIP_PATH, 'r')
        success, data = try_password_cp437(zf, pwd)
        zf.close()

        if success:
            print(f"\n*** SUCCESS! Password found: {pwd!r} (CP437 encoding) ***")
            print(f"First 100 bytes: {data[:100]}")
            found = True
            break

        # Try gbk
        zf = zipfile.ZipFile(ZIP_PATH, 'r')
        success, data = try_password_gbk(zf, pwd)
        zf.close()

        if success:
            print(f"\n*** SUCCESS! Password found: {pwd!r} (GBK encoding) ***")
            print(f"First 100 bytes: {data[:100]}")
            found = True
            break

        print(f"  FAILED")

    if not found:
        print("\n" + "=" * 60)
        print("Step 1 failed - none of the passwords worked.")
        print("=" * 60)

        # Step 2: Try bkcrack-style known-plaintext approach using pure Python
        print("\n" + "=" * 60)
        print("Step 2: Known-plaintext attack (pure Python)")
        print("=" * 60)
        known_plaintext_attack()

def known_plaintext_attack():
    """
    Attempt a known-plaintext attack on ZipCrypto.
    ZIP Crypto uses a 96-bit internal state based on 3x 32-bit keys (key0, key1, key2).
    With 12 bytes of known plaintext, we can recover the internal key state.
    """
    # Known phrases that might appear
    known_phrases = [
        b"\xe5\xba\x94\xe5\xa6\x82\xe6\x98\xaf",  # 应如是 in UTF-8
        b"dandan",
        b"DERA",
        b"\xe8\xa7\x89\xe9\x86\x92",  # 觉醒 in UTF-8
        b"\xe6\x84\x8f\xe5\xbf\x97",  # 意志 in UTF-8
    ]

    print("This requires bkcrack tool which is not currently installed.")
    print("Known plaintext phrases to try with bkcrack:")
    for i, phrase in enumerate(known_phrases):
        try:
            print(f"  [{i}] {phrase.decode('utf-8')!r} (hex: {phrase.hex()})")
        except:
            print(f"  [{i}] hex: {phrase.hex()}")

    print("\nTo use bkcrack (install from https://github.com/kimci86/bkcrack):")
    print(f"  bkcrack -C \"{ZIP_PATH}\" -c \"{TARGET_FILE}\" -p plaintext.bin")

    # Try to find the file offset in the zip to extract encrypted data
    try:
        with open(ZIP_PATH, 'rb') as f:
            zip_data = f.read()

        # Find the target filename in the zip
        target_bytes = TARGET_FILE.encode('utf-8')
        pos = zip_data.find(target_bytes)
        if pos > 0:
            print(f"\nFound '{TARGET_FILE}' in zip at offset {pos}")

        # Also try with CP437 encoding
        try:
            target_cp437 = TARGET_FILE.encode('cp437')
            if target_cp437 != target_bytes:
                pos2 = zip_data.find(target_cp437)
                if pos2 > 0:
                    print(f"Found '{TARGET_FILE}' (CP437) at offset {pos2}")
        except:
            pass

        print(f"\nTotal zip file size: {len(zip_data)} bytes")
    except Exception as e:
        print(f"Error reading zip: {e}")

    print("\n" + "=" * 60)
    print("FAILED: Could not recover password.")
    print("=" * 60)

if __name__ == "__main__":
    main()
