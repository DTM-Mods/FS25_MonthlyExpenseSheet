"""Runs the mod's real Lua outside the game and renders what the sheet draws to a PNG.

python -I tests/preview.py <pylib dir with lupa> <out.png> [income]

Game functions are stubbed: drawFilledRect / renderText calls are recorded and drawn with Pillow.
Money comes in through the real FSBaseMission.addMoney hook, with made-up sample charges.
"""
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from lupa.lua51 import LuaRuntime  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

MOD = Path(__file__).resolve().parent.parent
OUT = sys.argv[2]
SHOW_INCOME = len(sys.argv) > 3 and sys.argv[3] == "income"
W, H = 1920, 1080

texts = dict(re.findall(r'<text name="([^"]+)"><en>(.*?)</en></text>', (MOD / "modDesc.xml").read_text(encoding="utf8")))
# a few of the game's own finance titles, so the preview shows real-looking names
texts.update({
    "finance_newVehiclesCost": "New Vehicles", "finance_newAnimalsCost": "New Animals",
    "finance_vehicleRunningCost": "Vehicle Running Costs", "finance_vehicleLeasingCost": "Leasing Costs",
    "finance_propertyMaintenance": "Property Maintenance", "finance_wagePayment": "Wages",
    "finance_purchaseFuel": "Fuel", "finance_purchaseSeeds": "Seeds", "finance_purchaseFertilizer": "Fertilizer",
    "finance_loanInterest": "Loan Interest", "finance_soldProducts": "Sold Products", "finance_animalUpkeep": "Animal Upkeep",
    "finance_soldAnimals": "Sold Animals", "finance_soldVehicles": "Sold Vehicles", "finance_missionIncome": "Contracts",
    "finance_propertyIncome": "Property Income", "finance_productionCosts": "Production Costs",
})

fonts = {}


def font(size, bold):
    key = (size, bold)
    if key not in fonts:
        fonts[key] = ImageFont.truetype("C:/Windows/Fonts/" + ("segoeuib.ttf" if bold else "segoeui.ttf"), size)
    return fonts[key]


draw_calls = []
text_state = {"bold": False, "align": 0, "color": (1, 1, 1, 1)}


def py_rect(x, y, w, h, r, g, b, a):
    draw_calls.append(("rect", x, y, w, h, (r, g, b, a)))


def py_text(x, y, size, value):
    draw_calls.append(("text", x, y, size, value, dict(text_state)))


def py_width(size, value):
    px = max(1, round(size * H))
    return font(px, text_state["bold"]).getlength(value) / W


lua = LuaRuntime(unpack_returned_tuples=True)
g = lua.globals()
g.py_rect, g.py_text, g.py_width = py_rect, py_text, py_width
g.py_bold = lambda v: text_state.__setitem__("bold", bool(v))
g.py_align = lambda v: text_state.__setitem__("align", int(v))
g.py_color = lambda r, gg, b, a: text_state.__setitem__("color", (r, gg, b, a))
g.py_texts = lua.table_from(texts)

lua.execute(r"""
g_currentModName = "FS25_MonthlyExpenseSheet"
g_currentModDirectory = ""
Utils = {
    prependedFunction = function(old, new) return function(...) new(...) return old(...) end end,
    appendedFunction = function(old, new) return function(...) old(...) return new(...) end end,
    getNoNil = function(v, d) if v == nil then return d end return v end
}
FSBaseMission = {addMoney = function() end}
FSCareerMissionInfo = {saveToXMLFile = function() end}
PlayerInputComponent = {registerGlobalPlayerActionEvents = function() end}
FarmManager = {SPECTATOR_FARM_ID = 0, FARM_ID_SEND_NUM_BITS = 4}
listeners = {}
function addModEventListener(l) table.insert(listeners, l) end
function Class(t, base) return {__index = t} end
Event = {new = function(mt) return setmetatable({}, mt) end}
function InitEventClass() end
RenderText = {ALIGN_LEFT = 0, ALIGN_CENTER = 1, ALIGN_RIGHT = 2}
Input = {MOUSE_BUTTON_LEFT = 1, MOUSE_BUTTON_WHEEL_UP = 4, MOUSE_BUTTON_WHEEL_DOWN = 5}
InputAction = {MENU_BACK = "MENU_BACK", MES_TOGGLE_SHEET = "MES_TOGGLE_SHEET", MENU_PAGE_PREV = "PREV",
    MENU_PAGE_NEXT = "NEXT", MENU_AXIS_UP_DOWN = "UD", MENU_AXIS_LEFT_RIGHT = "LR"}
g_i18n = {
    getText = function(self, k) return py_texts[k] or ("MISSING " .. k) end,
    hasText = function(self, k) return py_texts[k] ~= nil end
}
g_server = {}
g_gui = {getIsGuiVisible = function() return false end}
g_inputBinding = {
    setContext = function() end, revertContext = function() end, setShowMouseCursor = function() end,
    registerActionEvent = function(self, a) return true, a end, setActionEventTextVisibility = function() end
}
g_farmManager = {getFarmById = function(self, id) return {name = "My Farm"} end, getFarms = function() return {} end}
g_currentMission = {
    environment = {currentYear = 13, currentPeriod = 8, currentDayInPeriod = 1, dayTime = 0},
    getFarmId = function() return 1 end
}
function drawFilledRect(...) py_rect(...) end
function renderText(...) py_text(...) end
function setTextBold(v) py_bold(v) end
function setTextAlignment(v) py_align(v) end
function setTextColor(...) py_color(...) end
function getTextWidth(size, value) return py_width(size, value) end
""")

for name in ["MonthlyExpenseSheet.lua", "MonthlyExpenseSheetEvents.lua", "MonthlyExpenseSheetDisplay.lua"]:
    lua.execute((MOD / "scripts" / name).read_text(encoding="utf8"))

# --- sample money: September (period 7) and October (period 8), Year 13, 4 days per month --------------
random.seed(13)
env = g.g_currentMission.environment
add_money_lua = lua.eval("function(amount, statistic, title) FSBaseMission.addMoney(g_currentMission, amount, 1, {statistic = statistic, title = title}, true) end")


def add_money(amount, statistic, title=None):
    add_money_lua(amount, statistic, title or "finance_" + statistic)


def at(period, day, hour, minute):
    env.currentPeriod, env.currentDayInPeriod, env.dayTime = period, day, (hour * 60 + minute) * 60000


for period, scale in [(7, 0.9), (8, 1.0)]:
    for day in range(1, 5):
        for hour in range(24):
            at(period, day, hour, 0)
            add_money(-random.uniform(30, 60) * scale, "vehicleRunningCost")
            if 6 <= hour <= 20:
                at(period, day, hour, 30)
                add_money(-random.uniform(150, 220) * scale, "wagePayment")
        at(period, day, 6, 0)
        add_money(-1800 * scale, "vehicleLeasingCost")
        add_money(-950, "propertyMaintenance")
        add_money(-1400 * scale, "newAnimalsCost") if day == 2 else None
        at(period, day, 0, 0)
        add_money(-540, "loanInterest")
        at(period, day, random.randint(8, 18), random.randint(0, 59))
        add_money(-random.uniform(2500, 4200) * scale, "purchaseFuel")
        at(period, day, random.randint(9, 17), random.randint(0, 59))
        add_money(random.uniform(30000, 90000) * scale, "soldProducts")
        at(period, day, 12, 15)
        add_money(random.uniform(8000, 14000), "missionIncome")
    at(period, 3, 10, 5)
    add_money(-206460 * scale, "other", "Pallet Costs")
    add_money(-115, "other", "Delivery Costs (2.5%)")
    add_money(-3150 * scale, "productionCosts")
    for day in range(1, 5):
        at(period, day, 0, 0)
        add_money(-random.uniform(700, 900), "animalUpkeep")
    at(period, 4, 18, 20)
    lua.globals().MonthlyExpenseSheet.record(1, -1250 * scale, "mesUntracked", "", 13, period, 4, 18, 20)
    at(period, 3, 14, 40)
    add_money(23850 * scale, "soldAnimals")
    add_money(4100, "soldAnimals")
at(8, 1, 12, 46)
add_money(-4500, "newVehiclesCost")

# --- open the sheet and draw it --------------------------------------------------------------------
display = g.MonthlyExpenseSheetDisplay
display.open()
if SHOW_INCOME:
    display.setShowIncome(True)
    display.changeSelection(1)
display.draw()

img = Image.new("RGB", (W, H), (70, 90, 50))
try:
    backdrop = Image.open(MOD / "previews" / "game_backdrop.png").convert("RGB").resize((W, H))
    img.paste(backdrop)
except FileNotFoundError:
    pass
d = ImageDraw.Draw(img, "RGBA")

for call in draw_calls:
    if call[0] == "rect":
        _, x, y, w, h, (r, gg, b, a) = call
        d.rectangle((x * W, (1 - y - h) * H, (x + w) * W - 1, (1 - y) * H - 1), fill=(int(r * 255), int(gg * 255), int(b * 255), int(a * 255)))
    else:
        _, x, y, size, value, st = call
        px = max(1, round(size * H))
        f = font(px, st["bold"])
        tw = f.getlength(value)
        left = x * W - (tw / 2 if st["align"] == 1 else tw if st["align"] == 2 else 0)
        r, gg, b, a = st["color"]
        d.text((left, (1 - y) * H), value, font=f, fill=(int(r * 255), int(gg * 255), int(b * 255), int(a * 255)), anchor="ls")

img.save(OUT)
print("saved", OUT, len(draw_calls), "draw calls")
