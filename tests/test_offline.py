"""Offline tests of FS25_MonthlyExpenseSheet: loads the mod's real Lua (in modDesc.xml order) into Lua 5.1
(lupa) with small stubs for the game engine, then drives the records, the multiplayer events and the sheet.

Usage: python tests/test_offline.py        (needs: pip install lupa)
Prints one line per test and a summary; exit code 0 = all passed. XFAIL = a known problem in the mod that the
test documents (does not fail the run); XPASS = that problem is gone, turn the test into a normal one.
Every test gets its own Lua state, so tests don't depend on each other."""
import copy
import os
import re
import struct
import sys
import traceback
import xml.etree.ElementTree as ET

import lupa.lua51 as lua51

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_DESC = ET.parse(os.path.join(PROJ, "modDesc.xml")).getroot()
SCRIPTS = [e.get("filename") for e in MOD_DESC.iter("sourceFile")]
ACTIONS = [e.get("name") for e in MOD_DESC.iter("action")]
TEXTS = {e.get("name"): e.findtext("en") for e in MOD_DESC.find("l10n").iter("text")}
# a few of the game's own texts
GAME_TEXTS = {"finance_wagePayment": "Wages", "finance_purchaseFuel": "Fuel", "finance_other": "Other",
              "finance_soldProducts": "Sold Products", "finance_propertyIncome": "Property Income",
              "finance_soldAnimals": "Sold Animals"}
# GIANTS' Lua knows `continue`; same replacement as .github/ci/fs25_mod.py (keeps the line numbers)
CONTINUE_RE = re.compile(r"(?<![\w.:'\"])continue(?![\w])")


def read_script(rel):
    src = open(os.path.join(PROJ, rel), "rb").read().decode("utf-8")
    return CONTINUE_RE.sub("do end", src)


# ---------------------------------------------------------------- engine stubs (Lua side)
ENGINE = r"""
T = {addMoneyCalls = {}, saveCalls = 0, eventClasses = {}, listeners = {}, events = {}, context = "PLAYER",
     cursor = false, log = {}, texts = {}, rects = 0, bold = false, align = 0}

print = function(...) table.insert(T.log, table.concat({...}, " ")) end      -- the mod's log lines
g_currentModName = "FS25_MonthlyExpenseSheet"
g_currentModDirectory = "C:/mods/FS25_MonthlyExpenseSheet/"
Utils = {
    prependedFunction = function(old, new) return function(...) new(...) return old(...) end end,
    appendedFunction = function(old, new) return function(...) old(...) new(...) end end,
    getNoNil = function(v, d) if v == nil then return d end return v end
}
function addModEventListener(l) table.insert(T.listeners, l) end

-- money
MoneyType = {
    OTHER = {statistic = "other", title = "finance_other"},
    WAGES = {statistic = "wagePayment", title = "finance_wagePayment"},
    FUEL = {statistic = "purchaseFuel", title = "finance_purchaseFuel"},
    SOLD_PRODUCTS = {statistic = "soldProducts", title = "finance_soldProducts"},
    SOLD_ANIMALS = {statistic = "soldAnimals", title = "finance_soldAnimals"},
    PROPERTY_INCOME = {statistic = "propertyIncome", title = "finance_propertyIncome"}
}
FarmManager = {SPECTATOR_FARM_ID = 0, FARM_ID_SEND_NUM_BITS = 4}
g_farmManager = {
    farms = {[0] = {farmId = 0, name = "Spectator", money = 0}, [1] = {farmId = 1, name = "Farm One", money = 100000},
             [2] = {farmId = 2, name = "Farm Two", money = 50000}},
    userFarms = {},
    getFarms = function(self) return self.farms end,
    getFarmById = function(self, id) return self.farms[id] end,
    getFarmByUserId = function(self, userId) return self.farms[self.userFarms[userId] or -1] end
}
FSBaseMission = {}
function FSBaseMission.addMoney(mission, amount, farmId, moneyType, addChange, forceShowChange)
    table.insert(T.addMoneyCalls, {mission = mission, amount = amount, farmId = farmId, moneyType = moneyType})
    local farm = g_farmManager:getFarmById(farmId)
    if farm ~= nil and amount ~= nil then farm.money = farm.money + amount end
    return "addMoney result"
end
FSCareerMissionInfo = {saveToXMLFile = function(self) T.saveCalls = T.saveCalls + 1 end}

g_currentMission = setmetatable({
    environment = {currentYear = 13, currentPeriod = 8, currentDayInPeriod = 1, dayTime = 0},
    playerFarmId = 1,
    getFarmId = function(self) return self.playerFarmId end,
    hud = {shown = {}, showMoneyChange = function(self, moneyType, text) table.insert(self.shown, text or "") end},
    placeableSystem = {placeables = {}},
    animalSystem = {types = {{name = "GOAT", groupTitle = "Goats"}, {name = "COW"}}},
    missionInfo = setmetatable({savegameDirectory = "C:/savegame1"}, {__index = FSCareerMissionInfo}),
    userManager = {getUserIdByConnection = function(self, connection) return connection.userId end}
}, {__index = FSBaseMission})
g_fillTypeManager = {
    fillTypes = {[2] = {title = "Wheat"}, [3] = {title = "Flour"}, [4] = {title = "Bread"}, [5] = {title = "Cake"}},
    getFillTypeByIndex = function(self, index) return self.fillTypes[index] end
}
g_modManager = {
    mods = {{modName = "FS25_MonthlyExpenseSheet", title = "Self", modDir = "C:/mods/FS25_MonthlyExpenseSheet/"},
            {modName = "FS25_Delivery", title = "Delivery Mod", modDir = "C:/mods/FS25_Delivery/"}},
    getActiveMods = function(self) return self.mods end
}

-- classes the mod wraps
SellingStation = {}
function SellingStation.sellFillType(station, farmId, fillDelta, fillTypeIndex, extra)
    station.extra = extra
    g_currentMission:addMoney(fillDelta * 2, farmId, MoneyType.SOLD_PRODUCTS, true)
    return "sold", fillDelta * 2
end
PlaceableIncomePerHour = {}
function PlaceableIncomePerHour.onHourChanged(placeable)
    if placeable.broken then error("broken placeable") end
    g_currentMission:addMoney(placeable.income, placeable:getOwnerFarmId(), MoneyType.PROPERTY_INCOME, true)
    return "hour done"
end
ProductionPoint = {MAX_PRODUCTIONS = 3}
function ProductionPoint.new() return {} end
function ProductionPoint.staticHelper(n) return n * 2 end
function ProductionPoint.directSell(point, amount)
    g_currentMission:addMoney(amount, point.farmId, MoneyType.SOLD_PRODUCTS, true)
    return "done", amount
end
function ProductionPoint.outer(point, inner, amount)
    ProductionPoint.directSell(inner, amount)
    g_currentMission:addMoney(amount, point.farmId, MoneyType.SOLD_PRODUCTS, true)
end
AnimalSellEvent = {run = function(event, connection)
    g_currentMission:addMoney(event.price, event.farmId, MoneyType.SOLD_ANIMALS, true, true)
    return "animals sold"
end}
T.orig = {addMoney = FSBaseMission.addMoney, sellFillType = SellingStation.sellFillType,
          onHourChanged = PlaceableIncomePerHour.onHourChanged, save = FSCareerMissionInfo.saveToXMLFile,
          ppNew = ProductionPoint.new, ppDirectSell = ProductionPoint.directSell, animalRun = AnimalSellEvent.run}

-- network
function Class(class, base)
    if base ~= nil then setmetatable(class, {__index = base}) end
    return {__index = class}
end
Event = {new = function(mt) return setmetatable({}, mt) end}
function InitEventClass(class, name) T.eventClasses[name] = class end
function T_connection(isServer, userId)
    return {isServer = isServer, userId = userId, sent = {},
            getIsServer = function(self) return self.isServer end,
            sendEvent = function(self, event) table.insert(self.sent, event) end}
end
T.serverConnection = T_connection(true)
g_client = {getServerConnection = function() return T.serverConnection end}

-- texts
g_i18n = {
    modEnvironments = {FS25_Trading = {texts = {uwm_finance_expense = "Trading expense"}}},
    getText = function(self, key) local v = T_TEXTS[key]; if v == nil then error("missing text " .. tostring(key), 2) end; return v end,
    hasText = function(self, key) return T_TEXTS[key] ~= nil end,
    formatMoney = function(self, value) return string.format("$%d", value) end,
    formatPeriod = function(self, period, short)
        local name = ({"March", "April", "May", "June", "July", "August", "September", "October", "November",
                       "December", "January", "February"})[period]
        return short and name:sub(1, 3) or name
    end
}

-- input and drawing
RenderText = {ALIGN_LEFT = 0, ALIGN_CENTER = 1, ALIGN_RIGHT = 2}
Input = {MOUSE_BUTTON_LEFT = 1, MOUSE_BUTTON_WHEEL_UP = 4, MOUSE_BUTTON_WHEEL_DOWN = 5}
InputAction = {MENU_BACK = "MENU_BACK", MENU_PAGE_PREV = "PREV", MENU_PAGE_NEXT = "NEXT", MENU_AXIS_UP_DOWN = "UD",
               MENU_AXIS_LEFT_RIGHT = "LR"}
for name in T_ACTIONS:gmatch("%S+") do InputAction[name] = name end
PlayerInputComponent = {registerGlobalPlayerActionEvents = function(self) T.playerEventsRegistered = true end}
g_gui = {visible = false, getIsGuiVisible = function(self) return self.visible end}
g_inputBinding = {
    setContext = function(self, name) T.context = name; T.events[name] = {} end,
    revertContext = function(self) T.context = "PLAYER" end,
    setShowMouseCursor = function(self, show) T.cursor = show end,
    registerActionEvent = function(self, action, target, callback)
        T.events[T.context] = T.events[T.context] or {}
        T.events[T.context][action] = {target = target, callback = callback}
        return true, T.context .. ":" .. action
    end,
    setActionEventTextVisibility = function() end
}
function drawFilledRect() T.rects = T.rects + 1 end
function setTextBold(bold) T.bold = bold end
function setTextAlignment(align) T.align = align end
function setTextColor() end
function renderText(x, y, size, text)
    assert(type(text) == "string", "renderText without a string")
    table.insert(T.texts, {x = x, y = y, text = text, bold = T.bold, align = T.align})
end
function getTextWidth(size, text) return size * #text * 0.5 end

-- test helpers -------------------------------------------------------------------------------------
function eq(actual, expected, what)
    if actual ~= expected then
        error(string.format("%s: expected %s, got %s", what or "value", tostring(expected), tostring(actual)), 2)
    end
end
function T_listener() return T.listeners[1] end
function T_at(year, period, day, hour, minute)
    local e = g_currentMission.environment
    e.currentYear, e.currentPeriod, e.currentDayInPeriod, e.dayTime = year, period, day, (hour * 60 + minute) * 60000
end
function T_money(amount, farmId, moneyType) return g_currentMission:addMoney(amount, farmId or 1, moneyType, true) end
-- the recorded type, nil when there is none
function T_type(farmId, monthKey, statistic, title, isIncome)
    local month = (MonthlyExpenseSheet.farms[farmId] or {})[monthKey]
    return month ~= nil and month.types[statistic .. "|" .. title .. (isIncome and "+" or "-")] or nil
end
function T_count(tbl) local n = 0; for _ in pairs(tbl) do n = n + 1 end; return n end
-- all records as text, in a fixed order
function T_dump(months)
    local out, monthKeys = {}, {}
    for key in pairs(months) do table.insert(monthKeys, key) end
    table.sort(monthKeys)
    for _, key in ipairs(monthKeys) do
        local month, typeKeys = months[key], {}
        table.insert(out, string.format("M %d %d %d", key, month.year, month.period))
        for typeKey in pairs(month.types) do table.insert(typeKeys, typeKey) end
        table.sort(typeKeys)
        for _, typeKey in ipairs(typeKeys) do
            local t = month.types[typeKey]
            table.insert(out, string.format("T %s|%s|%s|%s|%s|%.3f|%d", typeKey, t.key, t.statistic, t.title,
                tostring(t.isIncome), t.amount, t.count))
        end
        for _, e in ipairs(month.entries) do
            table.insert(out, string.format("E %s|%d|%d|%d|%.3f|%d", e.typeKey, e.day, e.hour, e.minute, e.amount, e.count))
        end
    end
    return table.concat(out, "\n")
end
-- the sheet: draw it and look at the texts
function T_draw() T.texts = {}; T.rects = 0; T_listener():draw(); return #T.texts end
function T_find(text)
    for _, t in ipairs(T.texts) do if t.text == text then return t end end
    return nil
end
function T_has(text) return T_find(text) ~= nil end
function T_starting(prefix)
    for _, t in ipairs(T.texts) do if t.text:sub(1, #prefix) == prefix then return t.text end end
    return nil
end
function T_heading() T_draw(); return T_starting("MARCH") or T_starting("APRIL") or T_starting("MAY  ") or T_starting("JUNE")
    or T_starting("JULY") or T_starting("AUGUST") or T_starting("SEPTEMBER") or T_starting("OCTOBER")
    or T_starting("NOVEMBER") or T_starting("DECEMBER") or T_starting("JANUARY") or T_starting("FEBRUARY") end
function T_details() T_draw(); return T_starting("DETAILS: ") end
function T_press(action, value)
    local event = (T.events[T.context] or {})[action]
    if event == nil then error("action " .. tostring(action) .. " is not registered in context " .. T.context, 2) end
    event.callback(event.target, action, value or 1)
end
function T_click(text, button)
    local t = T_find(text)
    if t == nil then error("text not drawn: " .. text, 2) end
    T_listener():mouseEvent(t.x, t.y, true, false, button or Input.MOUSE_BUTTON_LEFT)
end
"""


# ---------------------------------------------------------------- one Lua state with the mod loaded
class Mod:
    def __init__(self, server=True, pre="", load_map=True):
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self.stream = []        # fake network stream: (kind, value) in the order written
        self.xml = {}           # open XML handles
        self.disk = {}          # saved XML files, path -> root element
        self.next_handle = 1
        g = self.lua.globals()
        g.T_TEXTS = self.lua.table_from({**TEXTS, **GAME_TEXTS})
        g.T_ACTIONS = " ".join(ACTIONS)
        self._stream_stubs(g)
        self._xml_stubs(g)
        self.lua.execute(ENGINE)
        self.lua.execute("g_server = %s" % ("{}" if server else "nil"))
        if pre:
            self.lua.execute(pre)
        for rel in SCRIPTS:
            self.lua.execute("local src, name = ...; assert(loadstring(src, name))()", read_script(rel), "@" + rel)
        if load_map:
            self.lua.execute('T_listener():loadMap("map.i3d")')

    def run(self, code):
        self.lua.execute(code)

    def ev(self, expr):
        return self.lua.eval(expr)

    # network stream: every read must match the kind (and bit count) that was written at that place
    def _stream_stubs(self, g):
        def writer(kind, check):
            def write(stream_id, value, bits=None):
                self.stream.append((kind, bits, check(value, bits)))
            return write

        def reader(kind):
            def read(stream_id, bits=None):
                assert self.stream, "read %s past the end of the stream" % kind
                k, b, v = self.stream.pop(0)
                assert (k, b) == (kind, bits), "read %s/%s but %s/%s was written" % (kind, bits, k, b)
                return v
            return read

        def uint(default_bits):
            def check(value, bits):
                bits = bits or default_bits
                assert value is not None and float(value).is_integer() and 0 <= value < 2 ** bits, \
                    "%r does not fit an unsigned %d bit integer" % (value, bits)
                return int(value)
            return check

        def int32(value, bits):
            assert value is not None and float(value).is_integer() and -2 ** 31 <= value < 2 ** 31, value
            return int(value)

        def float32(value, bits):
            return struct.unpack("f", struct.pack("f", value))[0]

        def string(value, bits):
            assert isinstance(value, str), "streamWriteString with %r" % (value,)
            return value

        def boolean(value, bits):
            assert isinstance(value, bool), "streamWriteBool with %r" % (value,)
            return value

        for name, kind, check in (("UIntN", "uintN", uint(0)), ("UInt8", "u8", uint(8)), ("UInt16", "u16", uint(16)),
                                  ("Int32", "i32", int32), ("Float32", "f32", float32), ("String", "str", string),
                                  ("Bool", "bool", boolean)):
            g["streamWrite" + name] = writer(kind, check)
            g["streamRead" + name] = reader(kind)

    # XML files: elements kept in memory, "saved" into self.disk
    def _xml_stubs(self, g):
        def parts(key):
            path, _, attr = key.partition("#")
            out = []
            for p in path.split("."):
                m = re.match(r"(\w+)\((\d+)\)$", p)
                out.append((m.group(1), int(m.group(2))) if m else (p, 0))
            return out, attr or None

        def find(handle, key, create=False):
            path, attr = parts(key)
            node = self.xml[handle][0]
            assert path[0][0] == node.tag, key
            for tag, index in path[1:]:
                children = [c for c in node if c.tag == tag]
                while create and len(children) <= index:
                    children.append(ET.SubElement(node, tag))
                if index >= len(children):
                    return None, attr
                node = children[index]
            return node, attr

        def get(handle, key):
            node, attr = find(handle, key)
            return None if node is None else node.get(attr)

        def setter(convert):
            def set_value(handle, key, value):
                assert value is not None, "nil written to " + key
                node, attr = find(handle, key, create=True)
                node.set(attr, convert(value))
            return set_value

        def as_int(value):
            assert float(value).is_integer(), "setXMLInt with %r" % (value,)
            return str(int(value))

        def as_str(value):
            assert isinstance(value, str), "setXMLString with %r" % (value,)
            return value

        def create(name, path, root):
            self.next_handle += 1
            self.xml[self.next_handle] = (ET.Element(root), path)
            return self.next_handle

        def load(name, path):
            if path not in self.disk:
                return 0
            self.next_handle += 1
            self.xml[self.next_handle] = (copy.deepcopy(self.disk[path]), path)
            return self.next_handle

        def save(handle):
            root, path = self.xml[handle]
            self.disk[path] = copy.deepcopy(root)

        def has(handle, key):
            node, attr = find(handle, key)
            return node is not None and (attr is None or node.get(attr) is not None)

        g.createXMLFile, g.loadXMLFile, g.saveXMLFile = create, load, save
        g.delete = lambda handle: self.xml.pop(handle)
        g.fileExists = lambda path: path in self.disk
        g.hasXMLProperty = has
        g.setXMLInt, g.setXMLFloat, g.setXMLString = setter(as_int), setter(repr), setter(as_str)
        g.setXMLBool = setter(lambda v: "true" if v else "false")
        g.getXMLString = get
        g.getXMLInt = lambda h, k: None if get(h, k) is None else int(get(h, k))
        g.getXMLFloat = lambda h, k: None if get(h, k) is None else float(get(h, k))
        g.getXMLBool = lambda h, k: None if get(h, k) is None else get(h, k) == "true"


TESTS = []


def test(func=None, xfail=None):
    def add(f):
        TESTS.append((f, xfail))
        return f
    return add(func) if func else add


# ================================================================ 1. loading and hooks
@test
def load_scripts_and_hooks_register():
    """all scripts from modDesc.xml load, the listener and every hook are in place, the game's functions still run"""
    assert SCRIPTS == ["scripts/MonthlyExpenseSheet.lua", "scripts/MonthlyExpenseSheetEvents.lua",
                       "scripts/MonthlyExpenseSheetDisplay.lua"], SCRIPTS
    m = Mod()
    m.run(r"""
    eq(#T.listeners, 1, "mod event listeners"); eq(T_listener(), MonthlyExpenseSheet, "listener")
    eq(T.eventClasses.MESRequestEvent, MESRequestEvent, "InitEventClass request")
    eq(T.eventClasses.MESDataEvent, MESDataEvent, "InitEventClass data")
    for _, name in ipairs({"loadMap", "deleteMap", "update", "draw", "mouseEvent"}) do
        eq(type(MonthlyExpenseSheet[name]), "function", "listener function " .. name)
    end
    assert(FSBaseMission.addMoney ~= T.orig.addMoney, "addMoney is not hooked")
    assert(SellingStation.sellFillType ~= T.orig.sellFillType, "sellFillType is not hooked")
    assert(PlaceableIncomePerHour.onHourChanged ~= T.orig.onHourChanged, "onHourChanged is not hooked")
    assert(FSCareerMissionInfo.saveToXMLFile ~= T.orig.save, "saveToXMLFile is not hooked")
    assert(AnimalSellEvent.run ~= T.orig.animalRun, "AnimalSellEvent.run is not hooked")
    assert(ProductionPoint.directSell ~= T.orig.ppDirectSell, "ProductionPoint functions are not wrapped")
    eq(ProductionPoint.new, T.orig.ppNew, "ProductionPoint.new must stay as it is")
    eq(ProductionPoint.MAX_PRODUCTIONS, 3, "ProductionPoint constant")
    eq(ProductionPoint.staticHelper(5), 10, "ProductionPoint function called without a point")

    -- the game's addMoney still gets its own arguments and its result comes back
    local result = g_currentMission:addMoney(-50, 1, MoneyType.FUEL, true)
    eq(result, "addMoney result", "addMoney result")
    eq(#T.addMoneyCalls, 1, "calls of the game's addMoney")
    local call = T.addMoneyCalls[1]
    eq(call.mission, g_currentMission, "mission"); eq(call.amount, -50, "amount"); eq(call.farmId, 1, "farm")
    eq(call.moneyType, MoneyType.FUEL, "money type")
    eq(g_farmManager.farms[1].money, 99950, "farm money")
    assert(T_type(1, 1308, "purchaseFuel", "finance_purchaseFuel", false) ~= nil, "the charge was not recorded")

    -- the key binding is registered together with the player's own
    PlayerInputComponent.registerGlobalPlayerActionEvents({})
    assert(T.playerEventsRegistered, "the game's registerGlobalPlayerActionEvents no longer runs")
    assert(T.events.PLAYER.MES_TOGGLE_SHEET ~= nil, "MES_TOGGLE_SHEET is not registered")
    """)


@test
def load_without_optional_game_parts():
    """classes and fields the code checks for can be missing: no Lua error anywhere in a whole session"""
    m = Mod(pre=r"""
    AnimalSellEvent = nil; g_modManager = nil
    g_currentMission.hud = nil; g_currentMission.animalSystem = nil; g_currentMission.missionInfo = nil
    g_i18n.formatMoney = nil; g_i18n.formatPeriod = nil; g_i18n.modEnvironments = nil
    """)
    m.run(r"""
    local l = T_listener()
    T_money(-120, 1, MoneyType.OTHER); T_money(-80, 1, nil); T_money(300, 1, MoneyType.SOLD_ANIMALS)
    eq(T_type(1, 1308, "other", "finance_other", false).amount, -120, "money of the game itself keeps its title")
    eq(MonthlyExpenseSheet.findAnimalType("5 goat"), nil, "findAnimalType without an animal system")
    eq(MonthlyExpenseSheet.getSavegameFilename(), nil, "savegame file without mission info")
    MonthlyExpenseSheet.saveToXMLFile(nil)
    l:update(1000); l:update(1000)
    MonthlyExpenseSheetDisplay.toggle(); l:update(16)
    assert(T_draw() > 20, "the sheet draws nothing")
    assert(T_has("- 120 $"), "amount with the fallback money format")
    eq(T_heading(), "OCTOBER  -  Year 13", "heading with the fallback month names")
    l:mouseEvent(0.5, 0.5, true, false, Input.MOUSE_BUTTON_LEFT)
    l:deleteMap()
    eq(T.context, "PLAYER", "deleteMap closes the open sheet")
    eq(T_count(MonthlyExpenseSheet.farms), 0, "records after deleteMap")
    """)
    # the other mod's event is hooked at loadMap, when it exists by then
    m2 = Mod(load_map=False)
    m2.run(r"""
    local ran = false
    ExcessAnimalsSoldEvent = {run = function(event) ran = MonthlyExpenseSheet.sellingAnimalType; return 1, 2 end}
    local before = ExcessAnimalsSoldEvent.run
    T_listener():loadMap("map.i3d")
    assert(ExcessAnimalsSoldEvent.run ~= before, "ExcessAnimalsSoldEvent.run is not hooked at loadMap")
    local a, b = ExcessAnimalsSoldEvent.run({message = "Excess animals sold - 5 goat"})
    eq(a + b, 3, "results of the wrapped run"); eq(ran.name, "GOAT", "animal type found from the message")
    eq(MonthlyExpenseSheet.sellingAnimalType, nil, "marker after the run")
    """)


@test
def texts_and_actions_exist_in_moddesc():
    """every mes_* text and MES_* action the Lua uses is declared in modDesc.xml"""
    src = "".join(read_script(s) for s in SCRIPTS)
    used = set(re.findall(r'"(mes_\w+)"', src))
    assert len(used) >= 20, used
    missing = sorted(k for k in used if k not in TEXTS)
    assert not missing, "texts missing in modDesc.xml: %s" % missing
    actions = set(re.findall(r"InputAction\.(MES_\w+)", src))
    assert actions and actions <= set(ACTIONS), (actions, ACTIONS)
    for action in ACTIONS:
        assert "input_" + action in TEXTS, "no input_%s text" % action
        assert MOD_DESC.find("inputBinding/actionBinding[@action='%s']" % action) is not None, action


# ================================================================ 2. records
@test
def record_merges_same_hour():
    """charges of one type in one in-game hour become one entry; another hour or type starts a new one"""
    m = Mod()
    m.run(r"""
    local R = MonthlyExpenseSheet.record
    R(1, -100, "wagePayment", "finance_wagePayment", 13, 8, 2, 9, 5)
    R(1, -50, "wagePayment", "finance_wagePayment", 13, 8, 2, 9, 40)
    R(1, -30, "purchaseFuel", "finance_purchaseFuel", 13, 8, 2, 9, 41)
    R(1, -25, "wagePayment", "finance_wagePayment", 13, 8, 2, 9, 50)     -- merges past the fuel entry
    R(1, -10, "wagePayment", "finance_wagePayment", 13, 8, 2, 10, 0)     -- next hour
    R(1, 75, "wagePayment", "finance_wagePayment", 13, 8, 2, 10, 1)      -- a refund is income: its own type
    R(2, -1, "wagePayment", "finance_wagePayment", 13, 8, 2, 10, 1)      -- another farm

    local month = MonthlyExpenseSheet.farms[1][1308]
    eq(month.year, 13, "year"); eq(month.period, 8, "period")
    eq(T_count(month.types), 3, "types")
    local wages = month.types["wagePayment|finance_wagePayment-"]
    eq(wages.amount, -185, "wages amount"); eq(wages.count, 4, "wages charges"); eq(wages.isIncome, false, "wages side")
    eq(wages.key, "wagePayment|finance_wagePayment-", "type key")
    local refund = month.types["wagePayment|finance_wagePayment+"]
    eq(refund.amount, 75, "refund amount"); eq(refund.isIncome, true, "refund side")
    eq(#month.entries, 4, "entries")
    local first = month.entries[1]
    eq(first.amount, -175, "merged amount"); eq(first.count, 3, "merged count"); eq(first.minute, 50, "minute of the last charge")
    eq(first.day, 2, "day"); eq(first.hour, 9, "hour")
    eq(month.entries[3].amount, -10, "next hour entry"); eq(month.entries[3].count, 1, "next hour count")
    eq(#MonthlyExpenseSheet.farms[2][1308].entries, 1, "entries of farm 2")
    """)


@test
def add_money_filter_and_time():
    """the addMoney hook: what is ignored, the default type, and the in-game date and time of the entry"""
    m = Mod()
    m.run(r"""
    T_at(13, 8, 3, 14, 37)
    T_money(0.004, 1, MoneyType.FUEL)                       -- too small
    T_money(-500, FarmManager.SPECTATOR_FARM_ID, MoneyType.FUEL)
    g_currentMission:addMoney(nil, 1, MoneyType.FUEL)
    g_currentMission:addMoney(-5, nil, MoneyType.FUEL)
    eq(T_count(MonthlyExpenseSheet.farms), 0, "farms with records after ignored money")
    eq(#T.addMoneyCalls, 4, "the game's addMoney ran every time")

    T_money(-42.5, 2, nil)                                   -- no money type: other, no title
    local other = T_type(2, 1308, "other", "", false)
    assert(other ~= nil, "money without a type is not recorded as other")
    eq(other.amount, -42.5, "amount")
    local entry = MonthlyExpenseSheet.farms[2][1308].entries[1]
    eq(entry.day, 3, "day"); eq(entry.hour, 14, "hour"); eq(entry.minute, 37, "minute")

    g_currentMission.environment.dayTime = 23 * 3600000 + 59 * 60000 + 59999
    local year, period, day, hour, minute = MonthlyExpenseSheet.getNow()
    eq(hour, 23, "last hour of the day"); eq(minute, 59, "last minute of the day")
    g_currentMission.environment = {}
    year, period, day, hour, minute = MonthlyExpenseSheet.getNow()
    eq(year * 100 + period, 101, "defaults without a date"); eq(day + hour + minute, 1, "default day and time")
    """)
    # on a multiplayer client nothing is recorded: the server keeps the records
    c = Mod(server=False)
    c.run(r"""
    T_money(-500, 1, MoneyType.FUEL)
    g_currentMission.hud:showMoneyChange(MoneyType.FUEL, "Some text")
    T_listener():update(1000); T_listener():update(1000)
    eq(T_count(MonthlyExpenseSheet.farms), 0, "records on a client")
    eq(T_count(MonthlyExpenseSheet.balances), 0, "balance checks on a client")
    """)


@test
def month_and_year_rollover():
    """each in-game month gets its own records; period 12 is followed by period 1 of the next year"""
    m = Mod()
    m.run(r"""
    eq(MonthlyExpenseSheet.getMonthKey(13, 8), 1308, "month key")
    T_at(13, 11, 4, 23, 59); T_money(-10, 1, MoneyType.FUEL)
    T_at(13, 12, 1, 0, 0);   T_money(-20, 1, MoneyType.FUEL)
    T_at(14, 1, 1, 0, 0);    T_money(-40, 1, MoneyType.FUEL)
    local months = MonthlyExpenseSheet.farms[1]
    eq(T_count(months), 3, "months")
    eq(months[1311].types["purchaseFuel|finance_purchaseFuel-"].amount, -10, "period 11")
    eq(months[1312].types["purchaseFuel|finance_purchaseFuel-"].amount, -20, "period 12")
    eq(months[1401].types["purchaseFuel|finance_purchaseFuel-"].amount, -40, "period 1 of the next year")
    eq(months[1401].year, 14, "year"); eq(months[1401].period, 1, "period")
    eq(#months[1312].entries, 1, "entries of period 12")

    local D = MonthlyExpenseSheetDisplay
    eq(D.getPreviousMonthKey(1401), 1312, "month before period 1")
    eq(D.getPreviousMonthKey(1312), 1311, "month before period 12")
    T_at(14, 1, 1, 8, 0)
    local keys = D.getSortedMonthKeys()
    eq(table.concat(keys, ","), "1311,1312,1401", "sorted months")
    """)


@test
def limits_months_and_entries():
    """only the newest 24 months and the newest 400 entries of a month are kept"""
    m = Mod()
    m.run(r"""
    eq(MonthlyExpenseSheet.MAX_MONTHS, 24, "MAX_MONTHS"); eq(MonthlyExpenseSheet.MAX_ENTRIES_PER_MONTH, 400, "MAX_ENTRIES")
    for year = 1, 3 do
        for period = 1, 12 do MonthlyExpenseSheet.record(1, -year, "other", "", year, period, 1, 0, 0) end
    end
    local months = MonthlyExpenseSheet.farms[1]
    eq(T_count(months), 24, "months kept")
    eq(months[112], nil, "the oldest year is gone"); assert(months[201] ~= nil and months[312] ~= nil, "newest months missing")

    -- 410 entries in one month (one per hour): the first 10 drop out, the type's total keeps everything
    for i = 0, 409 do
        MonthlyExpenseSheet.record(2, -1, "other", "", 5, 1, 1 + math.floor(i / 24), i % 24, 0)
    end
    local month = MonthlyExpenseSheet.farms[2][501]
    eq(#month.entries, 400, "entries kept")
    eq(month.entries[1].hour, 10, "oldest kept entry"); eq(month.entries[400].day, 18, "newest entry")
    eq(month.types["other|-"].amount, -410, "type total"); eq(month.types["other|-"].count, 410, "type charges")
    """)


@test
def category_selling_and_production():
    """sales at a selling station and a production point's direct sales are listed as "sold <product>" """
    m = Mod()
    m.run(r"""
    local station = {}
    local a, b = SellingStation.sellFillType(station, 1, 100, 2, "extra")
    eq(a, "sold", "first result"); eq(b, 200, "second result"); eq(station.extra, "extra", "further arguments")
    eq(MonthlyExpenseSheet.sellingFillType, nil, "fill type marker after the sale")
    eq(MonthlyExpenseSheet.sellingStation, nil, "station marker after the sale")
    local wheat = T_type(1, 1308, "mesSold", "Wheat", true)
    assert(wheat ~= nil, "the sale is not listed under the fill type"); eq(wheat.amount, 200, "amount")
    eq(T_type(1, 1308, "soldProducts", "finance_soldProducts", true), nil, "the sale under the game's own type")
    SellingStation.sellFillType(station, 1, 5, 99)           -- unknown fill type: the game's own type
    eq(T_type(1, 1308, "soldProducts", "finance_soldProducts", true).amount, 10, "sale of an unknown fill type")

    local mill = {farmId = 1, outputFillTypeIdsDirectSell = {[3] = true},
        activeProductions = {{outputs = {{type = 3}, {type = 4, sellDirectly = true}, {type = 5}, {type = 3}}}, {outputs = {{type = 9, sellDirectly = true}}}}}
    local bakery = {farmId = 1, activeProductions = {{outputs = {{type = 5, sellDirectly = true}}}}}
    eq(MonthlyExpenseSheet.getProductionSaleText(mill), "Flour, Bread, 9", "products sold directly")
    eq(MonthlyExpenseSheet.getProductionSaleText({}), "?", "production point without productions")
    local r1, r2 = ProductionPoint.directSell(mill, 700)
    eq(r1, "done", "first result"); eq(r2, 700, "second result")
    eq(T_type(1, 1308, "mesSold", "Flour, Bread, 9", true).amount, 700, "direct sale")
    eq(MonthlyExpenseSheet.productionPoint, nil, "marker after the call")
    ProductionPoint.outer(mill, bakery, 40)                  -- nested: the outer point is back after the inner call
    eq(T_type(1, 1308, "mesSold", "Cake", true).amount, 40, "inner point")
    eq(T_type(1, 1308, "mesSold", "Flour, Bread, 9", true).amount, 740, "outer point")
    eq(MonthlyExpenseSheet.productionPoint, nil, "marker after the nested call")
    ProductionPoint.directSell(mill, -15)                    -- a cost inside a production point is not a sale
    eq(T_type(1, 1308, "soldProducts", "finance_soldProducts", false).amount, -15, "cost of a production point")
    """)


@test
def category_generator_and_stale_marker():
    """hourly income of placeables is listed per placeable (numbered when the farm has several);
    a marker left behind by a game function that failed is cleared in update"""
    m = Mod()
    m.run(r"""
    local function placeable(config, name, farmId, income)
        return {configFileName = config, income = income, spec_incomePerHour = {}, getName = function() return name end,
                getOwnerFarmId = function() return farmId end}
    end
    local solar = placeable("solar.xml", "Solar Panel", 1, 30)
    local wind1, wind2 = placeable("wind.xml", "Wind Turbine", 1, 100), placeable("wind.xml", "Wind Turbine", 1, 110)
    local otherFarm = placeable("wind.xml", "Wind Turbine", 2, 90)
    local shed = placeable("wind.xml", "Wind Turbine", 1, 0); shed.spec_incomePerHour = nil
    g_currentMission.placeableSystem.placeables = {solar, wind1, otherFarm, shed, wind2}

    eq(PlaceableIncomePerHour.onHourChanged(solar), "hour done", "result of the game function")
    PlaceableIncomePerHour.onHourChanged(wind1); PlaceableIncomePerHour.onHourChanged(wind2)
    PlaceableIncomePerHour.onHourChanged(otherFarm)
    eq(MonthlyExpenseSheet.incomePlaceable, nil, "marker after the call")
    eq(T_type(1, 1308, "mesGenerator", "Solar Panel", true).amount, 30, "single placeable")
    eq(T_type(1, 1308, "mesGenerator", "Wind Turbine 1", true).amount, 100, "first of two")
    eq(T_type(1, 1308, "mesGenerator", "Wind Turbine 2", true).amount, 110, "second of two")
    eq(T_type(2, 1308, "mesGenerator", "Wind Turbine", true).amount, 90, "the other farm's only turbine")

    -- other money while a placeable is being paid keeps its own type
    MonthlyExpenseSheet.incomePlaceable = solar
    T_money(-5, 1, MoneyType.FUEL)
    eq(T_type(1, 1308, "purchaseFuel", "finance_purchaseFuel", false).amount, -5, "other money type")

    -- the game function fails: the marker stays until the next frame, then it is gone
    solar.broken = true
    local ok = pcall(PlaceableIncomePerHour.onHourChanged, solar)
    eq(ok, false, "the failing game function"); eq(MonthlyExpenseSheet.incomePlaceable, solar, "marker after the failure")
    MonthlyExpenseSheet.sellingFillType = 2; MonthlyExpenseSheet.sellingAnimalType = {}; MonthlyExpenseSheet.productionPoint = {}
    T_listener():update(16)
    eq(MonthlyExpenseSheet.incomePlaceable, nil, "placeable marker after update")
    eq(MonthlyExpenseSheet.sellingFillType, nil, "fill type marker after update")
    eq(MonthlyExpenseSheet.sellingAnimalType, nil, "animal marker after update")
    eq(MonthlyExpenseSheet.productionPoint, nil, "production point marker after update")
    """)


@test
def category_animals_and_popup_text():
    """animal sales are listed per animal type; money a mod announces with its own popup text moves under that text"""
    m = Mod()
    m.run(r"""
    local goat, cow = g_currentMission.animalSystem.types[1], g_currentMission.animalSystem.types[2]
    eq(AnimalSellEvent.run({husbandry = {spec_husbandryAnimals = {animalType = goat}}, price = 900, farmId = 1}), "animals sold", "result")
    AnimalSellEvent.run({object = {spec_husbandryAnimals = {animalType = cow}}, price = 400, farmId = 1})
    eq(MonthlyExpenseSheet.sellingAnimalType, nil, "marker after the sale")
    eq(T_type(1, 1308, "mesSold", "Goats", true).amount, 900, "type with a group title")
    eq(T_type(1, 1308, "mesSold", "Cow", true).amount, 400, "type without a group title")
    eq(MonthlyExpenseSheet.getAnimalTitle({name = "WATER_BUFFALO"}), "Water_buffalo", "title from the name")
    eq(MonthlyExpenseSheet.getAnimalTitle({}), "?", "title without a name")
    eq(MonthlyExpenseSheet.findAnimalType("Excess animals sold - 5 Goat"), goat, "animal named in a text")
    eq(MonthlyExpenseSheet.findAnimalType("nothing here"), nil, "text without an animal")

    -- popup of a mod: "Delivery Costs 12 - 3" -> listed as "Delivery Costs", numbers left out
    local hud = g_currentMission.hud
    T_at(13, 8, 2, 7, 15)
    T_money(-60, 1, MoneyType.OTHER); hud:showMoneyChange(MoneyType.OTHER, "Delivery Costs 12 - 3")
    T_money(-40, 1, MoneyType.OTHER); hud:showMoneyChange(MoneyType.OTHER, " - Delivery Costs 7")
    eq(#hud.shown, 2, "the game's showMoneyChange still runs")
    local popup = T_type(1, 1308, "mesPopup", "Delivery Costs", false)
    assert(popup ~= nil, "no row for the popup text"); eq(popup.amount, -100, "popup amount"); eq(popup.count, 2, "popup charges")
    eq(T_type(1, 1308, "other", "finance_other", false), nil, "the money is still listed under the old type")
    local entries, n = MonthlyExpenseSheet.farms[1][1308].entries, 0
    for _, e in ipairs(entries) do
        assert(e.typeKey ~= "other|finance_other-", "an entry of the old type is left")
        if e.typeKey == "mesPopup|Delivery Costs-" then n = n + 1; eq(e.amount, -100, "entry amount"); eq(e.count, 2, "entry count"); eq(e.minute, 15, "entry minute") end
    end
    eq(n, 1, "popup entries")

    -- animals sold by a mod's popup: one row per animal type
    T_money(250, 1, MoneyType.SOLD_ANIMALS); hud:showMoneyChange(MoneyType.SOLD_ANIMALS, "Excess animals - 5 goat")
    eq(T_type(1, 1308, "mesSold", "Goats", true).amount, 1150, "animals sold by popup")

    -- not moved: the popup is for another money type, has no text, or nothing was recorded just before
    T_money(-7, 1, MoneyType.FUEL); hud:showMoneyChange(MoneyType.WAGES, "Wrong type")
    T_money(-7, 1, MoneyType.FUEL); hud:showMoneyChange(MoneyType.FUEL, nil)
    T_money(-7, 1, MoneyType.FUEL); hud:showMoneyChange(MoneyType.FUEL, " 12 - ")
    hud:showMoneyChange(MoneyType.FUEL, "Second popup without new money")
    eq(T_type(1, 1308, "purchaseFuel", "finance_purchaseFuel", false).amount, -21, "money that keeps its type")
    eq(T_type(1, 1308, "mesPopup", "Wrong type", false), nil, "popup of another money type")
    eq(T_type(1, 1308, "mesPopup", "Second popup without new money", false), nil, "popup without money")
    """)


@test
def category_other_money_gets_mod_name():
    """the game's "other" money paid from another mod's script is listed under that mod's title"""
    m = Mod()
    m.run(r"""
    local pay = assert(loadstring("g_currentMission:addMoney(-75, 1, MoneyType.OTHER, true) return 1", "@C:/mods/FS25_Delivery/scripts/Delivery.lua"))
    pay(); pay()
    local t = T_type(1, 1308, "other", "finance_other@@Delivery Mod", false)
    assert(t ~= nil, "no row with the mod's title"); eq(t.amount, -150, "amount")
    eq(MonthlyExpenseSheet.getTypeName(t), "Delivery Mod", "name of the row")
    -- the mod's own type and title are kept
    local own = assert(loadstring("g_currentMission:addMoney(-9, 1, MoneyType.FUEL, true) return 1", "@C:/mods/FS25_Delivery/scripts/Fuel.lua"))
    own()
    eq(T_type(1, 1308, "purchaseFuel", "finance_purchaseFuel", false).amount, -9, "money with a real type")
    -- money from this mod's own directory or the game is not credited to a mod
    local game = assert(loadstring("g_currentMission:addMoney(-3, 1, MoneyType.OTHER, true) return 1", "@C:/mods/FS25_MonthlyExpenseSheet/x.lua"))
    game()
    eq(T_type(1, 1308, "other", "finance_other", false).amount, -3, "money of the game itself")
    """)


@test
def balance_check_untracked_changes():
    """a farm balance that changes without addMoney shows up as untracked; recorded money is not counted twice"""
    m = Mod()
    m.run(r"""
    local l, farm = T_listener(), g_farmManager.farms[1]
    l:update(16)                                   -- first check: only remembers the balances
    eq(T_count(MonthlyExpenseSheet.farms), 0, "records after the first check")
    T_money(-200, 1, MoneyType.FUEL)              -- goes through addMoney
    farm.money = farm.money + 5000                 -- a mod changes the balance directly
    g_farmManager.farms[0].money = 123             -- spectators are ignored
    l:update(500)
    eq(T_type(1, 1308, "mesUntracked", "", true), nil, "checked before the interval was over")
    l:update(500)
    local untracked = T_type(1, 1308, "mesUntracked", "", true)
    assert(untracked ~= nil, "the direct change was not recorded"); eq(untracked.amount, 5000, "untracked amount")
    eq(T_type(1, 1308, "purchaseFuel", "finance_purchaseFuel", false).amount, -200, "recorded money")
    eq(MonthlyExpenseSheet.farms[0], nil, "spectator farm"); eq(MonthlyExpenseSheet.farms[2], nil, "farm without changes")
    l:update(1000); l:update(1000)
    eq(untracked.count, 1, "the change is recorded once")
    farm.money = farm.money - 0.5; l:update(1000)  -- under 1: ignored
    eq(T_type(1, 1308, "mesUntracked", "", false), nil, "tiny change")
    farm.money = farm.money - 300; l:update(1000)
    eq(T_type(1, 1308, "mesUntracked", "", false).amount, -300, "untracked expense")
    """)


@test
def type_names():
    """the text shown for a category"""
    m = Mod()
    m.run(r"""
    local function name(statistic, title, isIncome)
        return MonthlyExpenseSheet.getTypeName({statistic = statistic, title = title, isIncome = isIncome == true})
    end
    eq(name("mesUntracked", ""), "Untracked balance changes", "untracked")
    eq(name("mesPopup", "Delivery Costs"), "Delivery Costs", "popup text")
    eq(name("mesSold", "Wheat"), "Sold Wheat", "sold")
    eq(name("mesGenerator", "Wind Turbine 2"), "Generator: Wind Turbine 2", "generator")
    eq(name("other", "finance_other@@Delivery Mod"), "Delivery Mod", "mod that paid")
    eq(name("wagePayment", "finance_wagePayment"), "Wages", "the game's text of the title")
    eq(name("other", "uwm_finance_expense"), "Trading expense", "text of another mod")
    eq(name("other", "uwm_finance_depotExpense"), "Uwm depot expense", "unknown text key as words")
    eq(name("other", "Delivery Costs (2.5%)"), "Delivery Costs (2.5%)", "plain text")
    eq(name("purchaseFuel", ""), "Fuel", "the game's text of the statistic")
    eq(name("other", "", true), "Other", "other, with the game's finance_other text")
    eq(name("", nil, false), "Other expenses", "no statistic and no title")
    T_TEXTS.finance_other = nil                                -- without that text: the mod's own
    eq(name("other", "", true), "Other income", "other income")
    eq(name("other", "", false), "Other expenses", "other expenses")
    eq(name("other", "finance_other", false), "Other expenses", "other with the game's title")
    eq(name("harvestIncome", "finance_unknownKey"), "Harvest Income", "statistic as words")
    eq(MonthlyExpenseSheet.keyToWords("finance"), "finance", "key with nothing left")
    eq(MonthlyExpenseSheet.findModText("nope"), nil, "text no mod has")
    """)


@test
def savegame_round_trip():
    """saving with the savegame and loading again gives the same records"""
    m = Mod()
    m.run(r"""
    T_at(13, 7, 4, 22, 10); T_money(-1234.5, 1, MoneyType.WAGES); T_money(-10.25, 1, MoneyType.WAGES)
    T_at(13, 8, 1, 6, 0);   T_money(-99, 1, nil); T_money(4100, 1, MoneyType.SOLD_ANIMALS)
    MonthlyExpenseSheet.record(1, -115, "other", 'Delivery Costs (2.5%) <"&">', 13, 8, 1, 6, 30)
    T_at(14, 1, 2, 0, 5);   T_money(-7, 2, MoneyType.FUEL)
    SAVED = T_dump(MonthlyExpenseSheet.farms[1]); SAVED2 = T_dump(MonthlyExpenseSheet.farms[2])
    g_currentMission.missionInfo:saveToXMLFile()
    eq(T.saveCalls, 1, "the game's own save still runs")
    eq(MonthlyExpenseSheet.getSavegameFilename(), "C:/savegame1/monthlyExpenseSheet.xml", "file name")
    """)
    assert list(m.disk) == ["C:/savegame1/monthlyExpenseSheet.xml"], list(m.disk)
    assert not m.xml, "XML handle left open after saving"
    root = m.disk["C:/savegame1/monthlyExpenseSheet.xml"]
    assert root.tag == "monthlyExpenseSheet" and len(root.findall("farm")) == 2, ET.tostring(root)
    m.run(r"""
    MonthlyExpenseSheet.farms = {junk = true}
    MonthlyExpenseSheet.loadFromXMLFile()
    eq(T_count(MonthlyExpenseSheet.farms), 2, "farms loaded")
    eq(T_dump(MonthlyExpenseSheet.farms[1]), SAVED, "farm 1 after loading")
    eq(T_dump(MonthlyExpenseSheet.farms[2]), SAVED2, "farm 2 after loading")
    assert(T.log[#T.log]:find("Loaded records from C:/savegame1/monthlyExpenseSheet.xml", 1, true), "no log line for loading")
    -- loaded records go on like before: same hour merges into the loaded entry
    T_at(14, 1, 2, 0, 50); T_money(-3, 2, MoneyType.FUEL)
    eq(#MonthlyExpenseSheet.farms[2][1401].entries, 1, "entries after another charge")
    eq(MonthlyExpenseSheet.farms[2][1401].entries[1].amount, -10, "merged amount")
    """)
    assert not m.xml, "XML handle left open after loading"
    # loadMap on the server reads the file; a new savegame (no file, no directory) starts empty
    m.run(r"""
    MonthlyExpenseSheet.farms = {}
    T_listener():loadMap("map.i3d")
    eq(T_count(MonthlyExpenseSheet.farms), 2, "farms after loadMap")
    g_currentMission.missionInfo.savegameDirectory = "C:/savegame2"; T_listener():loadMap("map.i3d")
    eq(T_count(MonthlyExpenseSheet.farms), 0, "farms of a savegame without a file")
    g_currentMission.missionInfo.savegameDirectory = nil
    MonthlyExpenseSheet.loadFromXMLFile(); g_currentMission.missionInfo:saveToXMLFile()
    """)
    assert len(m.disk) == 1, list(m.disk)
    # a client neither loads nor saves
    c = Mod(server=False)
    c.disk["C:/savegame1/monthlyExpenseSheet.xml"] = root
    c.run(r"""
    T_listener():loadMap("map.i3d")
    eq(T_count(MonthlyExpenseSheet.farms), 0, "records loaded on a client")
    MonthlyExpenseSheet.farms[1] = {}
    g_currentMission.missionInfo.savegameDirectory = "C:/client"; g_currentMission.missionInfo:saveToXMLFile()
    """)
    assert list(c.disk) == ["C:/savegame1/monthlyExpenseSheet.xml"], list(c.disk)


# ================================================================ 3. multiplayer events
SAMPLE_RECORDS = r"""
T_at(13, 7, 4, 22, 10); T_money(-1234.5, 1, MoneyType.WAGES); T_money(-10.25, 1, MoneyType.WAGES)
T_at(13, 8, 1, 6, 0);   T_money(-99, 1, nil); T_money(4100, 1, MoneyType.SOLD_ANIMALS)
MonthlyExpenseSheet.record(1, -115, "other", "Delivery Costs (2.5%)", 13, 8, 1, 6, 30)
T_at(13, 8, 4, 23, 59); T_money(-0.5, 1, MoneyType.FUEL)
T_at(13, 8, 2, 9, 0);   T_money(-77, 2, MoneyType.FUEL)
"""


@test
def request_event_stream_and_server_answer():
    """MESRequestEvent: the farm survives the stream; the server answers only the player's own farm"""
    m = Mod()
    m.run(SAMPLE_RECORDS + r"""
    local sent = MESRequestEvent.new(1)
    eq(getmetatable(sent).__index, MESRequestEvent, "class of the event")
    sent:writeStream(1, T.serverConnection)
    """)
    assert m.stream == [("uintN", 4, 1)], m.stream
    m.run(r"""
    g_farmManager.userFarms = {[7] = 1, [8] = 2}
    local client = T_connection(false, 7)
    local received = MESRequestEvent.emptyNew()
    received:readStream(1, client)
    eq(received.farmId, 1, "farm read from the stream")
    eq(#client.sent, 1, "answers to the requesting connection")
    local answer = client.sent[1]
    eq(getmetatable(answer).__index, MESDataEvent, "class of the answer")
    eq(answer.farmId, 1, "farm of the answer"); eq(answer.months, MonthlyExpenseSheet.farms[1], "months of the answer")
    eq(#T.serverConnection.sent, 0, "events sent anywhere else")

    -- another farm's records are not handed out, nor to a player without a farm
    local nosy = T_connection(false, 8); MESRequestEvent.new(1):run(nosy)
    eq(#nosy.sent, 0, "answers for another farm")
    local stranger = T_connection(false, 99); MESRequestEvent.new(1):run(stranger)
    eq(#stranger.sent, 0, "answers for a player without a farm")
    -- a farm without records gets an empty answer
    g_farmManager.farms[3] = {farmId = 3, money = 0}; g_farmManager.userFarms[9] = 3
    local newFarm = T_connection(false, 9); MESRequestEvent.new(3):run(newFarm)
    eq(#newFarm.sent, 1, "answers for a farm without records"); eq(next(newFarm.sent[1].months), nil, "its months")
    -- on a client (the event came from the server) nothing happens
    local fromServer = T_connection(true, 7); MESRequestEvent.new(1):run(fromServer)
    eq(#fromServer.sent, 0, "answers on a client")
    """)
    assert not m.stream, "stream not read to the end: %s" % m.stream


@test
def data_event_stream_round_trip():
    """MESDataEvent: all months, types and entries survive writeStream -> readStream"""
    m = Mod()
    m.run(SAMPLE_RECORDS + r"""
    local months = MonthlyExpenseSheet.farms[1]
    -- an entry whose type is gone is left out instead of breaking the stream
    table.insert(months[1308].entries, 2, {typeKey = "ghost|-", day = 1, hour = 1, minute = 1, amount = -1, count = 1})
    MESDataEvent.new(1, months):writeStream(5, T_connection(false, 7))
    table.remove(months[1308].entries, 2)
    EXPECTED = T_dump(months)
    """)
    kinds = [k for k, _, _ in m.stream]
    assert kinds[:5] == ["uintN", "u16", "u16", "u8", "u16"], kinds[:5]
    assert kinds.count("str") == 2 * 5, "strings in the stream: %d" % kinds.count("str")   # 5 types in 2 months
    m.run(r"""
    g_server = nil                                            -- now the receiving client
    local received = MESDataEvent.emptyNew()
    received:readStream(5, T.serverConnection)
    eq(received.farmId, 1, "farm")
    eq(T_dump(received.months), EXPECTED, "records after the stream")
    eq(received.months[1308].types["other|Delivery Costs (2.5%)-"].isIncome, false, "isIncome is a boolean")
    eq(T_dump(MonthlyExpenseSheetDisplay.getMonths()), EXPECTED, "records the sheet shows")
    """)
    assert not m.stream, "stream not read to the end: %s" % m.stream
    # nothing recorded: an empty answer is fine too
    m.run(r"""
    MESDataEvent.new(1, {}):writeStream(6, T.serverConnection)
    local empty = MESDataEvent.emptyNew(); empty:readStream(6, T.serverConnection)
    eq(next(empty.months), nil, "months of an empty answer")
    eq(next(MonthlyExpenseSheetDisplay.getMonths()), nil, "the sheet after an empty answer")
    """)
    assert not m.stream, m.stream


@test
def data_event_only_for_own_farm_on_client():
    """the received records are shown only on a client and only for the player's own farm"""
    c = Mod(server=False)
    c.run(r"""
    local D = MonthlyExpenseSheetDisplay
    local mine = {[1308] = {year = 13, period = 8, types = {}, entries = {}}}
    MESDataEvent.new(2, {[1307] = {year = 13, period = 7, types = {}, entries = {}}}):run(T.serverConnection)
    eq(next(D.getMonths()), nil, "another farm's records")
    MESDataEvent.new(1, mine):run(T.serverConnection)
    eq(D.getMonths(), mine, "the own farm's records")
    MESDataEvent.new(1, {}):run(T_connection(false, 7))       -- not from the server: ignored
    eq(D.getMonths(), mine, "records after an event that did not come from the server")
    T_listener():loadMap("map.i3d")                           -- next map: the old copy is gone
    eq(next(D.getMonths()), nil, "records after loading another map")
    """)
    # the server shows its own records, never a received copy
    s = Mod()
    s.run(r"""
    T_money(-5, 1, MoneyType.FUEL)
    MESDataEvent.new(1, {}):run(T_connection(false, 7))
    eq(MonthlyExpenseSheetDisplay.getMonths(), MonthlyExpenseSheet.farms[1], "months on the server")
    g_currentMission.playerFarmId = 2
    eq(next(MonthlyExpenseSheetDisplay.getMonths()), nil, "months of a farm without records")
    """)


@test
def client_requests_data_when_opening():
    """a client asks the server when the sheet opens and every 10 s while it is open"""
    c = Mod(server=False)
    c.run(r"""
    local l, D, sent = T_listener(), MonthlyExpenseSheetDisplay, T.serverConnection.sent
    g_currentMission.playerFarmId = 2
    l:update(20000); eq(#sent, 0, "requests while the sheet is closed")
    D.open()
    eq(#sent, 1, "requests when opening"); eq(getmetatable(sent[1]).__index, MESRequestEvent, "class of the request")
    eq(sent[1].farmId, 2, "farm of the request")
    T_draw(); assert(T_has("Loading from server..."), "no loading text while waiting")
    assert(T_has("Nothing recorded yet. Every money change from now on will show up here."), "no empty text")
    l:update(9999); eq(#sent, 1, "requests before the interval is over")
    l:update(2);    eq(#sent, 2, "requests after 10 s")
    l:update(5000); eq(#sent, 2, "requests in the next interval")

    local month = {year = 13, period = 8, types = {}, entries = {}}
    MonthlyExpenseSheet.getType(month, "purchaseFuel", "finance_purchaseFuel", false).amount = -450
    MESDataEvent.new(2, {[1308] = month}):run(T.serverConnection)
    T_draw()
    assert(not T_has("Loading from server..."), "loading text after the answer")
    assert(T_has("Fuel") and T_has("- $450"), "the received category is not drawn")
    D.close(); l:update(20000); eq(#sent, 2, "requests after closing")
    """)
    # the server never asks
    s = Mod()
    s.run(r"""
    MonthlyExpenseSheetDisplay.open(); T_listener():update(20000)
    eq(#T.serverConnection.sent, 0, "requests on the server")
    T_draw(); assert(not T_has("Loading from server..."), "loading text on the server")
    """)


# ================================================================ 4. the sheet
@test
def totals_and_category_order():
    """totals per side; categories of one side, biggest first, equal amounts by key"""
    m = Mod()
    m.run(r"""
    local D, R = MonthlyExpenseSheetDisplay, MonthlyExpenseSheet.record
    R(1, -100, "other", "a", 13, 8, 1, 0, 0); R(1, -300, "other", "c", 13, 8, 1, 1, 0); R(1, -300, "other", "b", 13, 8, 1, 2, 0)
    R(1, -1000, "other", "d", 13, 8, 1, 3, 0); R(1, 50, "other", "e", 13, 8, 1, 4, 0); R(1, 2500, "other", "f", 13, 8, 1, 5, 0)
    local month = MonthlyExpenseSheet.farms[1][1308]
    local expenses, income = D.getTotals(month)
    eq(expenses, -1700, "expenses"); eq(income, 2550, "income")
    local e0, i0 = D.getTotals(nil); eq(e0 + i0, 0, "totals without a month")

    local titles = {}
    for _, t in ipairs(D.getCategories(month, false)) do table.insert(titles, t.title) end
    eq(table.concat(titles, ","), "d,b,c,a", "expense categories")
    titles = {}
    for _, t in ipairs(D.getCategories(month, true)) do table.insert(titles, t.title) end
    eq(table.concat(titles, ","), "f,e", "income categories")
    eq(#D.getCategories(nil, false), 0, "categories without a month")
    """)


@test
def money_and_month_formatting():
    """amounts through the game's formatter or the built-in one; month names with a fallback"""
    m = Mod()
    m.run(r"""
    local D = MonthlyExpenseSheetDisplay
    eq(D.formatMoney(-1234.5), "$1235", "the game's formatter gets the rounded absolute amount")
    eq(D.getMonthName(1, false), "March", "the game's month name"); eq(D.getMonthName(12, true), "Feb", "short name")
    g_i18n.formatMoney = nil; g_i18n.formatPeriod = nil
    eq(D.formatMoney(0), "0 $", "0"); eq(D.formatMoney(999.4), "999 $", "999.4"); eq(D.formatMoney(999.5), "1,000 $", "999.5")
    eq(D.formatMoney(-123456), "123,456 $", "-123456"); eq(D.formatMoney(1234567.2), "1,234,567 $", "1234567.2")
    eq(D.formatMoney(-12), "12 $", "-12")
    eq(D.getMonthName(8, false), "October", "fallback name"); eq(D.getMonthName(8, true), "Oct", "short fallback name")
    eq(D.getMonthName(13, false), "?", "period out of range"); eq(D.getMonthName(nil, true), "?", "no period")
    g_i18n.formatPeriod = function() return "" end
    eq(D.getMonthName(1, true), "Mar", "fallback when the game gives no name")
    """)


@test
def open_close_and_input_context():
    """opening sets the sheet's own input context with its keys and the mouse cursor; closing gives it all back"""
    m = Mod()
    m.run(r"""
    local l, D = T_listener(), MonthlyExpenseSheetDisplay
    PlayerInputComponent.registerGlobalPlayerActionEvents({})
    eq(T_draw(), 0, "texts drawn while closed")
    T_press("MES_TOGGLE_SHEET")                                -- Left Alt + M
    eq(T.context, "MES_SHEET", "input context"); eq(T.cursor, true, "mouse cursor")
    for _, action in ipairs({"MENU_BACK", "MES_TOGGLE_SHEET", "PREV", "NEXT", "UD", "LR"}) do
        assert(T.events.MES_SHEET[action] ~= nil, action .. " is not registered while the sheet is open")
    end
    assert(T_draw() > 20 and T.rects > 5, "the open sheet draws nothing")
    assert(T_has("MONTHLY EXPENSE SHEET"), "title"); assert(T_has("Farm One   |   Year 13"), "farm name and year")
    D.open(); eq(T.context, "MES_SHEET", "context after opening twice")
    T_press("MES_TOGGLE_SHEET")                                -- the same key closes
    eq(T.context, "PLAYER", "input context after closing"); eq(T.cursor, false, "mouse cursor after closing")
    eq(T_draw(), 0, "texts drawn after closing")
    D.close(); eq(T.context, "PLAYER", "context after closing twice")

    T_press("MES_TOGGLE_SHEET"); T_press("MENU_BACK")          -- Esc closes
    eq(T.context, "PLAYER", "input context after Esc")

    -- not over a menu: does not open, and closes when a menu comes up
    g_gui.visible = true; D.toggle()
    eq(T.context, "PLAYER", "opened over a menu")
    g_gui.visible = false; D.toggle(); l:update(16); eq(T.context, "MES_SHEET", "open without a menu")
    g_gui.visible = true; l:update(16)
    eq(T.context, "PLAYER", "still open under a menu"); eq(T_draw(), 0, "texts drawn under a menu")
    """)


@test
def draw_rows_totals_and_details():
    """what the sheet shows for a month: category rows, last month, totals, and the selected category's charges"""
    m = Mod()
    m.run(r"""
    T_at(13, 7, 1, 8, 0);  T_money(-200, 1, MoneyType.WAGES)
    T_at(13, 8, 3, 9, 5);  T_money(-300, 1, MoneyType.WAGES)
    T_at(13, 8, 3, 9, 30); T_money(-300, 1, MoneyType.WAGES)
    T_at(13, 8, 3, 10, 5); T_money(-1000, 1, MoneyType.FUEL)
    T_at(13, 8, 4, 12, 0); T_money(-1000.4, 1, MoneyType.WAGES)
    MonthlyExpenseSheetDisplay.open()
    T_draw()
    assert(T_has("OCTOBER  -  Year 13"), "month heading")
    assert(T_has("SEP") and T_has("OCT"), "month tabs"); assert(T_has("EXPENSES") and T_has("INCOME"), "side tabs")
    for _, text in ipairs({"Category", "Charges", "Amount", "Last month", "TOTAL EXPENSES", "TOTAL INCOME", "Net for month",
                           "Date / time", "ESC", "Close", "Q / E", "Prev / Next month", "Select category", "Expenses / Income"}) do
        assert(T_has(text), "not drawn: " .. text)
    end
    -- rows: Wages (1,600 in 3 charges, 200 last month) above Fuel (1,000 in 1, nothing last month)
    local wages, fuel = T_find("Wages"), T_find("Fuel")
    assert(wages ~= nil and fuel ~= nil, "category rows"); assert(wages.y > fuel.y, "the bigger category is not on top")
    eq(wages.bold, true, "the selected row is bold"); eq(fuel.bold, false, "other rows are not bold")
    assert(T_has("- $1600") and T_has("- $1000") and T_has("3") and T_has("1"), "amounts and charges of the rows")
    assert(T_has("$200") and T_has("$0"), "last month's amounts")
    assert(T_has("- $2600"), "total expenses"); assert(T_has("+ $0"), "total income")
    -- details of the selected category, newest first, merged charges marked
    assert(T_has("DETAILS: Wages"), "details title")
    local newest, merged = T_find("Oct 4   12:00"), T_find("Oct 3   09:30   (x2)")
    assert(newest ~= nil and merged ~= nil, "detail rows"); assert(newest.y > merged.y, "newest charge is not on top")
    assert(T_has("- $600"), "amount of the merged charge")
    assert(not T_has("Oct 3   10:05"), "a charge of another category is in the details")

    T_press("UD", -1)                                          -- down: Fuel
    T_draw()
    assert(T_has("DETAILS: Fuel") and T_has("Oct 3   10:05"), "details of the second category")
    T_press("LR", 1)                                           -- right: income, nothing there
    T_draw()
    assert(T_has("Nothing recorded this month yet."), "empty side"); eq(T_starting("DETAILS: "), nil, "details of nothing")
    T_money(4000, 1, MoneyType.SOLD_ANIMALS)
    T_draw()
    assert(T_has("Sold Animals") and T_has("+ $4000") and T_has("+ $1400"), "income row and the month's net")
    T_press("LR", -1)
    eq(T_details(), "DETAILS: Wages", "back on the expenses side")
    """)


@test
def change_month_keys():
    """Q / E step through the months that have records"""
    m = Mod()
    m.run(r"""
    local R = MonthlyExpenseSheet.record
    R(1, -1, "other", "x", 13, 4, 1, 0, 0); R(1, -1, "other", "x", 13, 6, 1, 0, 0); R(1, -1, "other", "x", 13, 7, 1, 0, 0)
    MonthlyExpenseSheetDisplay.open()                          -- October: nothing recorded yet
    eq(T_heading(), "OCTOBER  -  Year 13", "month when opening"); assert(T_has("Nothing recorded this month yet."), "empty month")
    T_press("PREV"); eq(T_heading(), "SEPTEMBER  -  Year 13", "previous from the empty current month")
    T_press("PREV"); eq(T_heading(), "AUGUST  -  Year 13", "previous")
    T_press("PREV"); eq(T_heading(), "JUNE  -  Year 13", "previous skips months without records")
    T_press("PREV"); eq(T_heading(), "JUNE  -  Year 13", "previous at the oldest month")
    T_press("NEXT"); eq(T_heading(), "AUGUST  -  Year 13", "next")
    T_press("NEXT"); T_press("NEXT"); eq(T_heading(), "SEPTEMBER  -  Year 13", "next at the newest month")

    -- an empty month between recorded ones (reached by its tab): steps to its neighbours
    MonthlyExpenseSheetDisplay.close(); T_at(13, 5, 1, 0, 0); MonthlyExpenseSheetDisplay.open()
    T_press("NEXT"); eq(T_heading(), "AUGUST  -  Year 13", "next from an empty month in between")
    MonthlyExpenseSheetDisplay.close(); MonthlyExpenseSheetDisplay.open()
    T_press("PREV"); eq(T_heading(), "JUNE  -  Year 13", "previous from an empty month in between")

    -- no records at all: nothing to step to
    g_currentMission.playerFarmId = 2
    T_press("PREV"); T_press("NEXT"); eq(T_heading(), "JUNE  -  Year 13", "month without any records")
    """)


@test(xfail="MonthlyExpenseSheetDisplay.lua:282 - next month from the newest (empty) month jumps to the oldest month")
def change_month_next_from_empty_current_month():
    """E in the current month, which has no records yet, must not jump back to the oldest month"""
    m = Mod()
    m.run(r"""
    local R = MonthlyExpenseSheet.record
    R(1, -1, "other", "x", 13, 4, 1, 0, 0); R(1, -1, "other", "x", 13, 6, 1, 0, 0); R(1, -1, "other", "x", 13, 7, 1, 0, 0)
    MonthlyExpenseSheetDisplay.open()                          -- October, nothing recorded yet
    T_press("NEXT")
    local heading = T_heading()
    assert(heading == "OCTOBER  -  Year 13" or heading == "SEPTEMBER  -  Year 13", "next month went to " .. heading)
    """)


@test
def month_tabs_window():
    """six month tabs at most, the selected month always among them"""
    m = Mod()
    m.run(r"""
    for period = 1, 10 do MonthlyExpenseSheet.record(1, -1, "other", "x", 13, period, 1, 0, 0) end
    T_at(13, 10, 1, 0, 0)
    MonthlyExpenseSheetDisplay.open()
    local short = {"MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"}
    local function tabs()
        T_draw()
        local shown = {}
        for _, name in ipairs(short) do if T_has(name) then table.insert(shown, name) end end
        return table.concat(shown, " ")
    end
    eq(tabs(), "JUL AUG SEP OCT NOV DEC", "tabs at the newest month")
    for _ = 1, 4 do T_press("PREV") end
    eq(tabs(), "JUN JUL AUG SEP OCT NOV", "tabs around August"); eq(T_heading(), "AUGUST  -  Year 13", "selected month")
    for _ = 1, 9 do T_press("PREV") end
    eq(tabs(), "MAR APR MAY JUN JUL AUG", "tabs at the oldest month")
    """)


@test
def category_selection_and_scrolling():
    """up / down move the selection, the list of 14 rows scrolls with it and stops at both ends"""
    m = Mod()
    m.run(r"""
    for i = 1, 20 do MonthlyExpenseSheet.record(1, -i * 10, "other", string.format("Cat %02d", i), 13, 8, 1, i, 0) end
    MonthlyExpenseSheetDisplay.open()
    local function rows()
        T_draw()
        local n, first, last = 0, nil, nil
        for i = 20, 1, -1 do
            local name = string.format("Cat %02d", i)
            if T_has(name) then n = n + 1; first = first or name; last = name end
        end
        return n, first, last
    end
    local n, first, last = rows()
    eq(n, 14, "rows shown"); eq(first, "Cat 20", "first row"); eq(last, "Cat 07", "last row")
    eq(T_starting("DETAILS: "), "DETAILS: Cat 20", "selected at the start")
    for _ = 1, 13 do T_press("UD", -1) end                      -- down to the last visible row: no scrolling yet
    n, first, last = rows(); eq(first, "Cat 20", "first row at row 14"); eq(T_starting("DETAILS: "), "DETAILS: Cat 07", "row 14")
    T_press("UD", -1)
    n, first, last = rows(); eq(n, 14, "rows after scrolling"); eq(first, "Cat 19", "first row after scrolling"); eq(last, "Cat 06", "last row after scrolling")
    for _ = 1, 50 do T_press("UD", -1) end                      -- stops at the last category
    n, first, last = rows(); eq(first, "Cat 14", "first row at the end"); eq(last, "Cat 01", "last row at the end")
    eq(T_starting("DETAILS: "), "DETAILS: Cat 01", "selected at the end")
    for _ = 1, 50 do T_press("UD", 1) end                       -- and back up to the first
    n, first, last = rows(); eq(first, "Cat 20", "first row back at the top"); eq(T_starting("DETAILS: "), "DETAILS: Cat 20", "selected at the top")

    -- changing the side or the month starts at the top again
    for _ = 1, 16 do T_press("UD", -1) end
    T_press("LR", 1); T_press("LR", -1)
    n, first = rows(); eq(first, "Cat 20", "first row after switching sides"); eq(T_starting("DETAILS: "), "DETAILS: Cat 20", "selected after switching sides")
    """)


@test
def mouse_clicks_hit_what_is_drawn():
    """clicking a drawn row, side tab, month tab or arrow does what it shows; clicks elsewhere do nothing"""
    m = Mod()
    m.run(r"""
    local l = T_listener()
    T_at(13, 6, 1, 8, 0); T_money(-10, 1, MoneyType.FUEL)
    T_at(13, 7, 1, 8, 0); T_money(-20, 1, MoneyType.FUEL)
    T_at(13, 8, 1, 8, 0); T_money(-1000, 1, MoneyType.FUEL); T_money(-600, 1, MoneyType.WAGES); T_money(-5, 1, nil)
    T_money(5000, 1, MoneyType.SOLD_ANIMALS)

    T_draw(); l:mouseEvent(0.5, 0.5, true, false, Input.MOUSE_BUTTON_LEFT)   -- closed: nothing happens
    MonthlyExpenseSheetDisplay.open()
    eq(T_details(), "DETAILS: Fuel", "selected at the start")
    T_click("Wages");           eq(T_details(), "DETAILS: Wages", "click on the second row")
    T_click("Other");           eq(T_details(), "DETAILS: Other", "click on the third row")
    local row = T_find("Fuel")
    l:mouseEvent(row.x, row.y, false, true, Input.MOUSE_BUTTON_LEFT)         -- button released: no click
    eq(T_details(), "DETAILS: Other", "after releasing the button over a row")
    l:mouseEvent(0.01, 0.01, true, false, Input.MOUSE_BUTTON_LEFT)           -- outside the panel
    l:mouseEvent(0.5, 0.2, true, false, Input.MOUSE_BUTTON_LEFT)             -- on the panel, on nothing
    eq(T_details(), "DETAILS: Other", "after clicks on nothing"); eq(T.context, "MES_SHEET", "still open")

    T_click("INCOME");   eq(T_details(), "DETAILS: Sold Animals", "click on INCOME")
    T_click("EXPENSES"); eq(T_details(), "DETAILS: Fuel", "click on EXPENSES")
    T_click("AUG");      eq(T_heading(), "AUGUST  -  Year 13", "click on a month tab")
    T_click(">");        eq(T_heading(), "SEPTEMBER  -  Year 13", "click on the right arrow")
    T_click("<"); T_click("<"); eq(T_heading(), "AUGUST  -  Year 13", "clicks on the left arrow")
    T_click("OCT");      eq(T_heading(), "OCTOBER  -  Year 13", "click on another month tab")
    """)


@test
def mouse_wheel_scrolls_list_or_details():
    """the wheel over the details scrolls the charges (3 per step, stops at both ends); elsewhere it moves the selection"""
    m = Mod()
    m.run(r"""
    local l = T_listener()
    -- 25 charges of one category, one per hour: 19 fit
    for i = 0, 24 do MonthlyExpenseSheet.record(1, -100 - i, "purchaseFuel", "finance_purchaseFuel", 13, 8, 1 + math.floor(i / 24), i % 24, i) end
    MonthlyExpenseSheet.record(1, -50, "wagePayment", "finance_wagePayment", 13, 8, 1, 3, 0)
    MonthlyExpenseSheetDisplay.open()
    local function shown()
        T_draw()
        local n = 0
        for _, t in ipairs(T.texts) do if t.text:find("^Oct %d   %d%d:%d%d$") then n = n + 1 end end
        return n
    end
    local function wheel(over, button)
        T_draw(); local t = T_find(over)
        l:mouseEvent(t.x, t.y, true, false, button)
    end
    eq(shown(), 19, "charges shown"); assert(T_has("Oct 2   00:24") and T_has("Oct 1   06:06"), "newest 19 charges")
    assert(not T_has("Oct 1   05:05"), "a 20th charge is shown")
    wheel("Date / time", Input.MOUSE_BUTTON_WHEEL_DOWN)
    eq(shown(), 19, "charges shown after scrolling"); assert(not T_has("Oct 1   22:22") and T_has("Oct 1   21:21"), "top after one step")
    assert(T_has("Oct 1   03:03") and not T_has("Oct 1   02:02"), "bottom after one step")
    eq(T_starting("DETAILS: "), "DETAILS: Fuel", "selection after scrolling the details")
    for _ = 1, 10 do wheel("Date / time", Input.MOUSE_BUTTON_WHEEL_DOWN) end
    eq(shown(), 19, "charges shown at the end"); assert(T_has("Oct 1   00:00") and T_has("Oct 1   18:18"), "oldest 19 charges")
    assert(not T_has("Oct 1   19:19"), "scrolled past the end")
    for _ = 1, 10 do wheel("Date / time", Input.MOUSE_BUTTON_WHEEL_UP) end
    shown(); assert(T_has("Oct 2   00:24"), "back at the newest charge")

    -- over the category list: the wheel moves the selection, and the details start at the top again
    wheel("Date / time", Input.MOUSE_BUTTON_WHEEL_DOWN)
    wheel("Category", Input.MOUSE_BUTTON_WHEEL_DOWN)
    eq(T_details(), "DETAILS: Wages", "wheel down over the list"); eq(shown(), 1, "charges of the other category")
    wheel("Category", Input.MOUSE_BUTTON_WHEEL_UP)
    eq(T_details(), "DETAILS: Fuel", "wheel up over the list"); assert(T_has("Oct 2   00:24"), "details start at the top")
    wheel("Category", Input.MOUSE_BUTTON_WHEEL_UP)
    eq(T_details(), "DETAILS: Fuel", "wheel up at the first category")
    """)


# ---------------------------------------------------------------- runner
def main():
    passed = failed = xfailed = xpassed = 0
    for func, xfail in TESTS:
        try:
            func()
        except Exception as ex:                    # LuaError, AssertionError or an error in a stub
            line = (str(ex).strip().splitlines() or [type(ex).__name__])[0]
            if xfail:
                xfailed += 1
                print("XFAIL %s: %s  [%s]" % (func.__name__, xfail, line))
            else:
                failed += 1
                print("FAIL  %s: %s" % (func.__name__, line))
                if "-v" in sys.argv:
                    traceback.print_exc()
            continue
        if xfail:
            xpassed += 1
            print("XPASS %s: the known problem is gone (%s)" % (func.__name__, xfail))
        else:
            passed += 1
            print("ok    %s" % func.__name__)
    print("%d tests: %d passed, %d failed, %d known problems (xfail), %d fixed (xpass) - %s"
          % (len(TESTS), passed, failed, xfailed, xpassed, "FAILED" if failed else "ALL OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
