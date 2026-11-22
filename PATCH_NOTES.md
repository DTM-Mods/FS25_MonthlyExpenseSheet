<p align="center">
  <img src="https://raw.githubusercontent.com/DTM-Mods/.github/main/assets/patch-notes.jpg" alt="Patch notes" width="100%">
</p>

# Patch notes

## 1.0.0.3

- Fix: pressing E (or the right arrow) in the current month before anything was recorded in it jumped back to the oldest month. It now goes to the newest month that has records.
- Fix: a saved entry whose category is missing from the savegame file now shows under Other instead of disappearing.
- Fix: animal names made of several words show with spaces (Water buffalo, not Water_buffalo).
- Offline tests (`tests/test_offline.py`, 29 tests), run by every build.

## 1.0.0.2

- Description in GIANTS' ModHub layout (category, price, upkeep or hotkeys at the top).

## 1.0.0.1

- Updated for the current game version: modDesc descVersion 116 (the game build of 2026-10-27; GIANTS TestRunner 0.9.24 accepts only 116).

## 1.0.0.0
- Meets the GIANTS ModHub checks (TestRunner): textures, icon and modDesc brought up to date.
- Errors are no longer hidden: they show in the log.

## 0.2.2.1

- The author now shows as **DTM Mods, PropaineX** in the mod list.

## 0.2.2.0
- Money from other mods shows its real name instead of a text key: Player Trading+ lines read "Player trade purchases" and the like, not `uwm_finance_expense`.
- A text key no mod knows shows as words ("Uwm depot expense") instead of the raw key.

## 0.2.1.0
- Vehicle sales show as one "Sold Vehicles" line.

## 0.2.0.0
- No more "Misc" lines: sales show what was sold ("Sold Wheat", "Sold Goats"), including production direct sales.
- Money from other mods shows that mod's name or its own popup text.
- Hourly income from generators, wind turbines, solar and towers is listed per building.

## 0.1.0.0
- First release: every money popup (the green and orange lines under your balance) is kept per month, so you can read back what you earned and spent after sleeping.
