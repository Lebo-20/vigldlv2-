
import asyncio
from gsheets import gsheet_manager

async def check_headers():
    if gsheet_manager.sheet:
        headers = gsheet_manager.sheet.row_values(1)
        print(f"Headers found: {headers}")
    else:
        print("Sheet not connected.")

if __name__ == "__main__":
    asyncio.run(check_headers())
