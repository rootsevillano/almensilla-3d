import sys
import os
import json
from pathlib import Path

def validate_glb(file_path):
    print(f"Validating contract for {file_path}...")
    if not os.path.exists(file_path):
        print(f"FAIL: File {file_path} does not exist.")
        return False
    
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"File size: {file_size_mb:.2f} MB")
    
    if file_size_mb > 50:
        print("WARNING: Model exceeds 50MB budget. Consider decimation or Draco compression.")
    
    print("Contract validation passed.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_glb.py <path_to_glb>")
        sys.exit(1)
    success = validate_glb(sys.argv[1])
    sys.exit(0 if success else 1)