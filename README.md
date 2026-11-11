<p align="center">
  <a href="https://github.com/DTM-Mods"><img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/dtm-header.jpg" alt="DTM Mods by PropaineX & Fennell" width="100%"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/icons/FS25_MonthlyExpenseSheet.png" alt="Monthly Expense Sheet Pro Edition icon" width="128">
</p>

<h1 align="center">Monthly Expense Sheet Pro Edition</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Farming%20Simulator-25-2E6B4F" alt="Farming Simulator 25">
  <a href="https://github.com/DTM-Mods/FS25_MonthlyExpenseSheet/releases/latest"><img src="https://img.shields.io/github/v/release/DTM-Mods/FS25_MonthlyExpenseSheet?label=version&color=D9A441" alt="Latest version"></a>
  <img src="https://img.shields.io/badge/multiplayer-supported-2E6B4F" alt="Multiplayer supported">
  <a href="https://github.com/DTM-Mods"><img src="https://img.shields.io/badge/DTM-Mods-143326" alt="DTM Mods"></a>
</p>

<p align="center">
  <b>Every money popup, recorded and sorted by month, so you can see where your money went.</b><br>
  <sub>by PropaineX</sub>
</p>

<p align="center">
  <a href="https://github.com/DTM-Mods/FS25_MonthlyExpenseSheet/releases/latest"><img src="https://img.shields.io/badge/Download-latest%20release-D9A441?style=for-the-badge&logo=github&logoColor=143326&labelColor=E9C77A" alt="Download the latest release"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/features.jpg" alt="Features" width="100%">
</p>

When you sleep, the money popups under your balance (top right) scroll by too fast to read. This mod records
every one of them, sorted by in-game month, so you can see where your money went.

<p align="center">
  <img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/how-to-use.jpg" alt="How to use" width="100%">
</p>

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

<p align="center">
  <img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/installation.jpg" alt="Installation" width="100%">
</p>

Download `FS25_MonthlyExpenseSheet.zip` from the [latest release](https://github.com/DTM-Mods/FS25_MonthlyExpenseSheet/releases/latest) and put it in `Documents/My Games/FarmingSimulator2025/mods`, without unzipping or renaming it. In multiplayer, the server and every player need the same version.

<p align="center">
  <img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/license.jpg" alt="License" width="100%">
</p>

MIT, see [LICENSE](LICENSE).

<details>
<summary><b>For developers</b>: files, building and tests</summary>

### Files

- `modDesc.xml`, `icon_MonthlyExpenseSheet.dds`
- `scripts/MonthlyExpenseSheet.lua`: records money changes, balance check, save / load
- `scripts/MonthlyExpenseSheetEvents.lua`: multiplayer request / data events
- `scripts/MonthlyExpenseSheetDisplay.lua`: the sheet (drawn on screen) and its controls
- `tests/preview.py`: runs the real Lua outside the game with sample data and renders the sheet to a PNG
- `previews/icon_mockup.py`: draws the icon

</details>

---

<p align="center">
  <a href="https://github.com/DTM-Mods"><img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/dtm-intro.gif" alt="DTM Mods by PropaineX & Fennell" width="420"></a><br>
  <sub>Part of <a href="https://github.com/DTM-Mods">DTM Mods</a> (Dead To Me) by PropaineX & Fennell</sub>
</p>
