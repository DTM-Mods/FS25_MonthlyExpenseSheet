# Monthly Expense Sheet Pro Edition (FS25)

A Farming Simulator 25 mod by PropaineX.

When you sleep, the money popups under your balance (top right) scroll by too fast to read. This mod records
every one of them, sorted by in-game month, so you can see where your money went.

## Use

- **Left Alt + M** opens / closes the sheet (can be changed in the controls menu).
- **Q / E**: previous / next month. **Up / Down**: select a category. **Left / Right**: expenses / income.
- Mouse: click the month tabs, the EXPENSES / INCOME tabs and categories; the wheel scrolls.
- **Esc** closes the sheet.

## What it shows

- Every expense and income category for the month, named like the popup, with the number of charges, the
  month's total and last month's total (red / green arrow for up / down).
- Every single charge in the selected category with its date and time. Small charges of the same kind in the
  same in-game hour are merged into one line.
- Total expenses, total income and net for the month.
- **Untracked balance changes**: money that changed without a popup, so the sheet always adds up to your balance.

Records are saved with the savegame (`monthlyExpenseSheet.xml`, last 24 months). Multiplayer: the server keeps the
records, each player sees their own farm.

## Files

- `modDesc.xml`, `icon_MonthlyExpenseSheet.dds`
- `scripts/MonthlyExpenseSheet.lua`: records money changes, balance check, save / load
- `scripts/MonthlyExpenseSheetEvents.lua`: multiplayer request / data events
- `scripts/MonthlyExpenseSheetDisplay.lua`: the sheet (drawn on screen) and its controls
- `tests/preview.py`: runs the real Lua outside the game with sample data and renders the sheet to a PNG
- `previews/icon_mockup.py`: draws the icon
