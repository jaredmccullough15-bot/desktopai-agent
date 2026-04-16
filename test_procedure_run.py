"""
Test running the Sherpa Sync procedure to debug why it's not working from the agent
"""
import sys
sys.path.insert(0, '.')

from modules.procedures import run_procedure

print("\n=== Testing Procedure Execution ===\n")

# Try to run the procedure
print("Attempting to run 'Sherpa Sync (Jared)' procedure...")
try:
    result = run_procedure("Sherpa Sync (Jared)", checkpoint_handler=None)
    print(f"\nProcedure result: {result}")
    if result:
        print("✅ Procedure completed successfully")
    else:
        print("❌ Procedure failed")
except Exception as e:
    print(f"❌ Exception occurred: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
