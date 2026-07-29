import os
import sys

# Adjust path to import from project root
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "crypto_signal_station"))

def run_tests():
    print("Running sanity checks...")
    errors = []

    # 1. Test Imports
    try:
        import crypto_signal_station.crypto_signal_pipeline
        import crypto_signal_station.daily_report
        import generate_site
        print("✅ Imports successful")
    except ImportError as e:
        errors.append(f"Failed to import module: {e}")

    # 2. Test Config
    if os.path.exists("crypto_signal_station/cryptos.yml"):
        print("✅ cryptos.yml found")
    else:
        errors.append("cryptos.yml missing")

    # 3. Test Data Folders
    missing_folders = []
    for sub in ["crypto", "stocks"]:
        path = os.path.join("crypto_history_csv", sub, "1d")
        if not os.path.exists(path):
            missing_folders.append(path)
    
    if not missing_folders:
        print("✅ Data folders exist")
    else:
        # Only error if parent exists (implies run happened), otherwise just warn
        if os.path.exists("crypto_history_csv"):
             errors.append(f"Data folders missing: {missing_folders}")

    # 4. Test Reports
    if os.path.exists("reports"):
        print("✅ Reports directory found")
    else:
        errors.append("Reports directory missing")

    if errors:
        print("\n❌ Sanity checks failed:")
        for err in errors:
            print(f" - {err}")
        sys.exit(1)
    else:
        print("\n✅ All Sanity Checks Passed!")
        sys.exit(0)

if __name__ == "__main__":
    run_tests()
