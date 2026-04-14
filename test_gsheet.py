
import asyncio
import logging
import sys

# Set UTF-8 for windows console
if sys.platform == 'win32':
    import codecs
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from gsheets import gsheet_manager

# Setup logging
logging.basicConfig(level=logging.INFO)

async def test():
    print("--- TESTING GOOGLE SHEETS ---")
    
    # 1. Check Authentication
    if gsheet_manager.sheet:
        print("✅ Authentication: SUCCESS")
        print(f"Connected to Sheet: {gsheet_manager.sheet.title}")
    else:
        print("❌ Authentication: FAILED")
        print("Check if the JSON file name matches and is in the correct folder.")
        return

    # 2. Try Logging a Test Row
    test_title = "TEST BOT VIGLOO " + str(id(gsheet_manager))
    print(f"Trying to log test drama: '{test_title}'...")
    
    success = gsheet_manager.log_drama(test_title, "SKIP", "Tes koneksi bot")
    if success:
        print("✅ Logging: SUCCESS")
    else:
        print("❌ Logging: FAILED")
        return

    # 3. Try Searching for the logged row
    print(f"Searching for '{test_title}' in spreadsheet...")
    record = gsheet_manager.find_drama(test_title)
    if record:
        print(f"✅ Search: SUCCESS")
        print(f"Data found: {record}")
    else:
        print("❌ Search: FAILED (Data might be cached or failed to write)")

if __name__ == "__main__":
    asyncio.run(test())
