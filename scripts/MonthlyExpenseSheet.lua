-- Monthly Expense Sheet (PropaineX)
-- Records every money change of every farm (FSBaseMission.addMoney on the server, the same changes that
-- pop up under the balance in the top right corner), sorted by in-game month, and saves them with the
-- savegame. Clients ask the server for their farm's records when they open the sheet.
--
-- Data per farm:  months[monthKey] = {year, period, types = {[typeKey] = type}, entries = {entry, ...}}
--   monthKey = year * 100 + period (period 1 = March, the game's first month of the year)
--   typeKey  = statistic .. "|" .. title .. "+" (income) or "-" (expense): one row per popup name, so mods that
--              charge under the game's "other" type with their own name (e.g. delivery costs) get their own row
--   type     = {key, statistic, title, isIncome, amount, count}
--   entry    = {typeKey, day, hour, minute, amount, count}; charges of the same type in the same in-game
--              hour are merged into one entry (running costs and wages come in many small pieces)

MonthlyExpenseSheet = {}
MonthlyExpenseSheet.MOD_NAME = g_currentModName
MonthlyExpenseSheet.MOD_DIRECTORY = g_currentModDirectory
MonthlyExpenseSheet.SAVE_FILENAME = "monthlyExpenseSheet.xml"
MonthlyExpenseSheet.MAX_MONTHS = 24
MonthlyExpenseSheet.MAX_ENTRIES_PER_MONTH = 400

MonthlyExpenseSheet.BALANCE_CHECK_INTERVAL = 1000
MonthlyExpenseSheet.UNTRACKED = "mesUntracked"
MonthlyExpenseSheet.GENERATOR = "mesGenerator"
MonthlyExpenseSheet.SOLD = "mesSold"
MonthlyExpenseSheet.POPUP = "mesPopup"
-- generic "other" money gets the paying mod's name appended to its title: title .. SOURCE_SEPARATOR .. mod title
MonthlyExpenseSheet.SOURCE_SEPARATOR = "@@"

-- placeable whose hourly income (generators, wind turbines, solar panels) is being paid right now
MonthlyExpenseSheet.incomePlaceable = nil
-- selling station and fill type being sold right now
MonthlyExpenseSheet.sellingStation = nil
MonthlyExpenseSheet.sellingFillType = nil
-- animal type sold at the animal dealer right now
MonthlyExpenseSheet.sellingAnimalType = nil
-- production point whose code is running right now (direct sell pays from inside it)
MonthlyExpenseSheet.productionPoint = nil
-- debug source -> mod title (false = not a mod)
MonthlyExpenseSheet.sourceMods = {}

MonthlyExpenseSheet.farms = {}
-- balance check: farmId -> {balance, recorded since then}
MonthlyExpenseSheet.balances = {}
MonthlyExpenseSheet.balanceTimer = 0

local function log(text, ...)
    print(string.format("[MonthlyExpenseSheet] " .. text, ...))
end

function MonthlyExpenseSheet.getMonthKey(year, period)
    return year * 100 + period
end

function MonthlyExpenseSheet.getNow()
    local environment = g_currentMission.environment
    local dayTime = environment.dayTime or 0
    local minutes = math.floor(dayTime / 60000)

    return environment.currentYear or 1, environment.currentPeriod or 1, environment.currentDayInPeriod or 1,
        math.floor(minutes / 60) % 24, minutes % 60
end

function MonthlyExpenseSheet.getFarmMonths(farmId)
    local months = MonthlyExpenseSheet.farms[farmId]
    if months == nil then
        months = {}
        MonthlyExpenseSheet.farms[farmId] = months
    end

    return months
end

function MonthlyExpenseSheet.getMonth(months, year, period)
    local monthKey = MonthlyExpenseSheet.getMonthKey(year, period)
    local month = months[monthKey]
    if month == nil then
        month = {year = year, period = period, types = {}, entries = {}}
        months[monthKey] = month
        MonthlyExpenseSheet.trimMonths(months)
    end

    return month
end

-- keeps only the newest MAX_MONTHS months
function MonthlyExpenseSheet.trimMonths(months)
    local keys = {}
    for monthKey in pairs(months) do
        table.insert(keys, monthKey)
    end
    table.sort(keys)

    for i = 1, #keys - MonthlyExpenseSheet.MAX_MONTHS do
        months[keys[i]] = nil
    end
end

function MonthlyExpenseSheet.getType(month, statistic, title, isIncome)
    local typeKey = statistic .. "|" .. (title or "") .. (isIncome and "+" or "-")
    local moneyType = month.types[typeKey]
    if moneyType == nil then
        moneyType = {key = typeKey, statistic = statistic, title = title, isIncome = isIncome, amount = 0, count = 0}
        month.types[typeKey] = moneyType
    end

    return moneyType
end

-- adds one money change; amount < 0 = expense
function MonthlyExpenseSheet.record(farmId, amount, statistic, title, year, period, day, hour, minute)
    local months = MonthlyExpenseSheet.getFarmMonths(farmId)
    local month = MonthlyExpenseSheet.getMonth(months, year, period)
    local moneyType = MonthlyExpenseSheet.getType(month, statistic, title, amount > 0)

    moneyType.amount = moneyType.amount + amount
    moneyType.count = moneyType.count + 1

    local entries = month.entries
    local last = nil
    for i = #entries, math.max(1, #entries - 20), -1 do
        local entry = entries[i]
        if entry.day ~= day or entry.hour ~= hour then
            break
        end
        if entry.typeKey == moneyType.key then
            last = entry
            break
        end
    end

    if last ~= nil then
        last.amount = last.amount + amount
        last.count = last.count + 1
        last.minute = minute
    else
        table.insert(entries, {typeKey = moneyType.key, day = day, hour = hour, minute = minute, amount = amount, count = 1})
        if #entries > MonthlyExpenseSheet.MAX_ENTRIES_PER_MONTH then
            table.remove(entries, 1)
        end
    end
end

function MonthlyExpenseSheet.onAddMoney(mission, amount, farmId, moneyType, ...)
    if g_server == nil or amount == nil or farmId == nil or math.abs(amount) < 0.005 then
        return
    end
    if farmId == FarmManager.SPECTATOR_FARM_ID then
        return
    end

    local statistic = "other"
    local title = ""
    if moneyType ~= nil then
        statistic = moneyType.statistic or statistic
        title = moneyType.title or title
    end

    local placeable = MonthlyExpenseSheet.incomePlaceable
    local fillType = MonthlyExpenseSheet.sellingFillType ~= nil and g_fillTypeManager:getFillTypeByIndex(MonthlyExpenseSheet.sellingFillType) or nil
    if fillType ~= nil and amount > 0 then
        statistic = MonthlyExpenseSheet.SOLD
        title = fillType.title
    elseif MonthlyExpenseSheet.sellingAnimalType ~= nil and amount > 0 then
        statistic = MonthlyExpenseSheet.SOLD
        title = MonthlyExpenseSheet.getAnimalTitle(MonthlyExpenseSheet.sellingAnimalType)
    elseif MonthlyExpenseSheet.productionPoint ~= nil and amount > 0 then
        statistic = MonthlyExpenseSheet.SOLD
        title = MonthlyExpenseSheet.getProductionSaleText(MonthlyExpenseSheet.productionPoint)
    elseif placeable ~= nil and moneyType == MoneyType.PROPERTY_INCOME then
        statistic = MonthlyExpenseSheet.GENERATOR
        title = MonthlyExpenseSheet.getGeneratorName(placeable, farmId)
    elseif statistic == "other" and (title == "" or title == "finance_other") then
        local modTitle = MonthlyExpenseSheet.getCallingMod()
        if modTitle ~= nil then
            title = title .. MonthlyExpenseSheet.SOURCE_SEPARATOR .. modTitle
        end
    end

    local year, period, day, hour, minute = MonthlyExpenseSheet.getNow()
    MonthlyExpenseSheet.record(farmId, amount, statistic, title, year, period, day, hour, minute)
    MonthlyExpenseSheet.lastRecord = {farmId = farmId, amount = amount, statistic = statistic, title = title, moneyType = moneyType,
        year = year, period = period, day = day, hour = hour, minute = minute}

    local balance = MonthlyExpenseSheet.balances[farmId]
    if balance ~= nil then
        balance.recorded = balance.recorded + amount
    end
end

-- title of the mod that called addMoney, nil when it was the game itself
function MonthlyExpenseSheet.getCallingMod()
    if debug == nil or debug.getinfo == nil or g_modManager == nil then
        return nil
    end

    for level = 3, 20 do
        local ok, info = pcall(debug.getinfo, level, "S")
        if not ok or info == nil then
            return nil
        end

        local source = info.source or ""
        local modTitle = MonthlyExpenseSheet.sourceMods[source]
        if modTitle == nil then
            modTitle = false
            for _, mod in ipairs(g_modManager:getActiveMods()) do
                if mod.modDir ~= nil and mod.modName ~= MonthlyExpenseSheet.MOD_NAME and source:find(mod.modDir, 1, true) then
                    modTitle = mod.title or mod.modName
                    break
                end
            end
            MonthlyExpenseSheet.sourceMods[source] = modTitle
        end
        if modTitle then
            return modTitle
        end
    end

    return nil
end

-- "5G Tower", or "5G Tower 2" when the farm owns more than one of the same
function MonthlyExpenseSheet.getGeneratorName(placeable, farmId)
    local name = placeable:getName() or "?"
    local number, count = 0, 0
    for _, other in ipairs(g_currentMission.placeableSystem.placeables) do
        if other.configFileName == placeable.configFileName and other:getOwnerFarmId() == farmId
            and other.spec_incomePerHour ~= nil then
            count = count + 1
            if other == placeable then
                number = count
            end
        end
    end

    if count > 1 then
        return string.format("%s %d", name, number)
    end
    return name
end

function MonthlyExpenseSheet.onIncomeHourChanged(placeable, superFunc, ...)
    MonthlyExpenseSheet.incomePlaceable = placeable
    local ok, result = pcall(superFunc, placeable, ...)
    MonthlyExpenseSheet.incomePlaceable = nil
    if not ok then
        error(result)
    end
    return result
end

function MonthlyExpenseSheet.onSellFillType(station, superFunc, farmId, fillDelta, fillTypeIndex, ...)
    MonthlyExpenseSheet.sellingStation = station
    MonthlyExpenseSheet.sellingFillType = fillTypeIndex
    local ok, result = pcall(superFunc, station, farmId, fillDelta, fillTypeIndex, ...)
    MonthlyExpenseSheet.sellingStation = nil
    MonthlyExpenseSheet.sellingFillType = nil
    if not ok then
        error(result)
    end
    return result
end

-- the products the production point is selling directly right now
function MonthlyExpenseSheet.getProductionSaleText(point)
    local products, seen = {}, {}
    local directSell = point.outputFillTypeIdsDirectSell or {}
    for _, production in ipairs(point.activeProductions or {}) do
        for _, output in ipairs(production.outputs or {}) do
            if (directSell[output.type] or output.sellDirectly) and not seen[output.type] then
                seen[output.type] = true
                local fillType = g_fillTypeManager:getFillTypeByIndex(output.type)
                table.insert(products, fillType ~= nil and fillType.title or tostring(output.type))
            end
        end
    end

    return #products > 0 and table.concat(products, ", ") or "?"
end

-- every ProductionPoint function marks the point as running, so money paid from inside it (direct sell) is
-- credited to it; the game's direct sell code is not in gameSource.zip, so no single function is named here
function MonthlyExpenseSheet.wrapProductionPoint()
    for name, func in pairs(ProductionPoint) do
        if type(func) == "function" and name ~= "new" then
            ProductionPoint[name] = function(point, ...)
                if type(point) ~= "table" then
                    return func(point, ...)
                end
                local previous = MonthlyExpenseSheet.productionPoint
                MonthlyExpenseSheet.productionPoint = point
                local results = {pcall(func, point, ...)}
                MonthlyExpenseSheet.productionPoint = previous
                if not results[1] then
                    error(results[2])
                end
                return unpack(results, 2, table.maxn(results))
            end
        end
    end
end

-- takes one money change back out (it is recorded again under another name)
function MonthlyExpenseSheet.unrecord(last)
    local month = MonthlyExpenseSheet.getMonth(MonthlyExpenseSheet.getFarmMonths(last.farmId), last.year, last.period)
    local moneyType = MonthlyExpenseSheet.getType(month, last.statistic, last.title, last.amount > 0)
    moneyType.amount = moneyType.amount - last.amount
    moneyType.count = moneyType.count - 1
    if moneyType.count <= 0 then
        month.types[moneyType.key] = nil
    end

    for i = #month.entries, 1, -1 do
        local entry = month.entries[i]
        if entry.typeKey == moneyType.key and entry.day == last.day and entry.hour == last.hour then
            entry.amount = entry.amount - last.amount
            entry.count = entry.count - 1
            if entry.count <= 0 then
                table.remove(month.entries, i)
            end
            break
        end
    end
end

-- "Goats"; one row per animal type, young and grown animals together
function MonthlyExpenseSheet.getAnimalTitle(animalType)
    if animalType.groupTitle ~= nil and animalType.groupTitle ~= "" then
        return animalType.groupTitle
    end
    local name = (animalType.name or "?"):lower()
    return (name:gsub("^%l", string.upper))
end

-- the animal type a popup text names, e.g. "Excess animals - 5 goat"
function MonthlyExpenseSheet.findAnimalType(text)
    local animalSystem = g_currentMission.animalSystem
    if animalSystem == nil or animalSystem.types == nil then
        return nil
    end
    text = text:lower()
    for _, animalType in ipairs(animalSystem.types) do
        if animalType.name ~= nil and text:find(animalType.name:lower(), 1, true) then
            return animalType
        end
    end
    return nil
end

function MonthlyExpenseSheet.onAnimalSellRun(event, superFunc, ...)
    local husbandry = event.husbandry or event.object
    local spec = type(husbandry) == "table" and husbandry.spec_husbandryAnimals or nil
    if spec ~= nil then
        MonthlyExpenseSheet.sellingAnimalType = spec.animalType
    elseif type(event.message) == "string" then
        -- FS25_ExcessAnimalsSold: "Excess animals sold - 5 goat"
        MonthlyExpenseSheet.sellingAnimalType = MonthlyExpenseSheet.findAnimalType(event.message)
    end
    local ok, result = pcall(superFunc, event, ...)
    MonthlyExpenseSheet.sellingAnimalType = nil
    if not ok then
        error(result)
    end
    return result
end

-- When a mod puts its own text in the money popup in the top right corner (e.g. "Excess animals - 5 Baby goats"),
-- the money it just paid is listed under that text instead; numbers are left out so every sale lands in one row.
function MonthlyExpenseSheet.onShowMoneyChange(object, moneyType, text, ...)
    local last = MonthlyExpenseSheet.lastRecord
    MonthlyExpenseSheet.lastRecord = nil
    if g_server == nil or last == nil or type(text) ~= "string" or text == "" or last.moneyType ~= moneyType then
        return
    end

    local title = text:gsub("%d+", ""):gsub("%s+", " "):gsub("^[%s%-]+", ""):gsub("[%s%-]+$", "")
    if title == "" then
        return
    end

    local statistic = MonthlyExpenseSheet.POPUP
    local animalType = moneyType == MoneyType.SOLD_ANIMALS and MonthlyExpenseSheet.findAnimalType(text) or nil
    if animalType ~= nil then
        statistic = MonthlyExpenseSheet.SOLD
        title = MonthlyExpenseSheet.getAnimalTitle(animalType)
    end

    MonthlyExpenseSheet.unrecord(last)
    MonthlyExpenseSheet.record(last.farmId, last.amount, statistic, title, last.year, last.period, last.day, last.hour, last.minute)
end

-- Catches money that changes without going through addMoney (some mods change the farm balance directly):
-- every second the farm balance is compared with the last balance plus what was recorded since, and any
-- difference is recorded as "Untracked balance changes".
function MonthlyExpenseSheet.checkBalances(dt)
    MonthlyExpenseSheet.balanceTimer = MonthlyExpenseSheet.balanceTimer - dt
    if MonthlyExpenseSheet.balanceTimer > 0 then
        return
    end
    MonthlyExpenseSheet.balanceTimer = MonthlyExpenseSheet.BALANCE_CHECK_INTERVAL

    for _, farm in pairs(g_farmManager:getFarms()) do
        local farmId = farm.farmId
        local money = farm.money
        if farmId ~= nil and farmId ~= FarmManager.SPECTATOR_FARM_ID and money ~= nil then
            local balance = MonthlyExpenseSheet.balances[farmId]
            if balance ~= nil then
                local difference = money - (balance.balance + balance.recorded)
                if math.abs(difference) >= 1 then
                    local year, period, day, hour, minute = MonthlyExpenseSheet.getNow()
                    MonthlyExpenseSheet.record(farmId, difference, MonthlyExpenseSheet.UNTRACKED, "", year, period, day, hour, minute)
                end
            end
            MonthlyExpenseSheet.balances[farmId] = {balance = money, recorded = 0}
        end
    end
end

-- A text from any mod's own l10n: mods' texts live in g_i18n.modEnvironments[modName].texts, which
-- g_i18n:hasText / getText without that mod's name don't see.
function MonthlyExpenseSheet.findModText(key)
    local environments = g_i18n ~= nil and g_i18n.modEnvironments or nil
    if type(environments) ~= "table" or type(key) ~= "string" then
        return nil
    end
    for _, environment in pairs(environments) do
        local texts = type(environment) == "table" and environment.texts or nil
        local text = type(texts) == "table" and texts[key] or nil
        if type(text) == "string" and text ~= "" then
            return text
        end
    end
    return nil
end

-- "uwm_finance_depotExpense" -> "Uwm depot expense"
function MonthlyExpenseSheet.keyToWords(key)
    local words = {}
    for part in key:gmatch("[^_]+") do
        if part ~= "finance" then
            local word = part:gsub("(%l)(%u)", "%1 %2"):lower()
            table.insert(words, word)
        end
    end
    local text = table.concat(words, " ")
    if text == "" then
        return key
    end
    return (text:gsub("^%l", string.upper))
end

-- text for a category; the money type's own l10n title when there is one
function MonthlyExpenseSheet.getTypeName(moneyType)
    local statistic = moneyType.statistic or ""
    if statistic == MonthlyExpenseSheet.UNTRACKED then
        return g_i18n:getText("mes_untracked", MonthlyExpenseSheet.MOD_NAME)
    end

    if statistic == MonthlyExpenseSheet.POPUP then
        return moneyType.title or "?"
    end
    if statistic == MonthlyExpenseSheet.SOLD then
        return g_i18n:getText("mes_sold", MonthlyExpenseSheet.MOD_NAME):format(moneyType.title or "?")
    end
    if statistic == MonthlyExpenseSheet.GENERATOR then
        return g_i18n:getText("mes_generator", MonthlyExpenseSheet.MOD_NAME):format(moneyType.title or "?")
    end

    -- the l10n key the popup uses; mods sometimes give plain text instead
    local title = moneyType.title or ""
    local separator = title:find(MonthlyExpenseSheet.SOURCE_SEPARATOR, 1, true)
    if separator ~= nil then
        return title:sub(separator + #MonthlyExpenseSheet.SOURCE_SEPARATOR)
    end
    if title ~= nil and title ~= "" then
        if g_i18n:hasText(title) then
            return g_i18n:getText(title)
        end
        -- a key from another mod's own texts (Player Trading+ registers "uwm_finance_expense" in its modDesc)
        local modText = MonthlyExpenseSheet.findModText(title)
        if modText ~= nil then
            return modText
        end
        if not title:find("^finance_") then
            -- a text key nobody knows: readable words instead of the raw key
            if title:find("^[%w_]+$") and title:find("_") then
                return MonthlyExpenseSheet.keyToWords(title)
            end
            return title
        end
    end

    if g_i18n:hasText("finance_" .. statistic) then
        return g_i18n:getText("finance_" .. statistic)
    end
    if statistic == "" or statistic == "other" then
        return g_i18n:getText(moneyType.isIncome and "mes_otherIncome" or "mes_otherExpense", MonthlyExpenseSheet.MOD_NAME)
    end

    -- "harvestIncome" -> "Harvest Income"
    local name = statistic:gsub("(%l)(%u)", "%1 %2"):gsub("_", " ")
    return (name:gsub("^%l", string.upper))
end

-- savegame ---------------------------------------------------------------------------------------------

function MonthlyExpenseSheet.getSavegameFilename()
    local missionInfo = g_currentMission ~= nil and g_currentMission.missionInfo or nil
    if missionInfo == nil or missionInfo.savegameDirectory == nil or missionInfo.savegameDirectory == "" then
        return nil
    end

    return missionInfo.savegameDirectory .. "/" .. MonthlyExpenseSheet.SAVE_FILENAME
end

function MonthlyExpenseSheet.saveToXMLFile(missionInfo)
    if g_server == nil or missionInfo == nil or missionInfo.savegameDirectory == nil then
        return
    end

    local filename = missionInfo.savegameDirectory .. "/" .. MonthlyExpenseSheet.SAVE_FILENAME
    local xmlFile = createXMLFile("monthlyExpenseSheet", filename, "monthlyExpenseSheet")
    if xmlFile == nil or xmlFile == 0 then
        log("Could not write %s", filename)
        return
    end

    local farmIndex = 0
    for farmId, months in pairs(MonthlyExpenseSheet.farms) do
        local farmKey = string.format("monthlyExpenseSheet.farm(%d)", farmIndex)
        setXMLInt(xmlFile, farmKey .. "#id", farmId)

        local monthIndex = 0
        for _, month in pairs(months) do
            local monthKey = string.format("%s.month(%d)", farmKey, monthIndex)
            setXMLInt(xmlFile, monthKey .. "#year", month.year)
            setXMLInt(xmlFile, monthKey .. "#period", month.period)

            local typeIndex = 0
            for _, moneyType in pairs(month.types) do
                local typeKey = string.format("%s.type(%d)", monthKey, typeIndex)
                setXMLString(xmlFile, typeKey .. "#statistic", moneyType.statistic)
                setXMLString(xmlFile, typeKey .. "#title", moneyType.title)
                setXMLBool(xmlFile, typeKey .. "#isIncome", moneyType.isIncome)
                setXMLFloat(xmlFile, typeKey .. "#amount", moneyType.amount)
                setXMLInt(xmlFile, typeKey .. "#count", moneyType.count)
                typeIndex = typeIndex + 1
            end

            for i, entry in ipairs(month.entries) do
                local entryKey = string.format("%s.entry(%d)", monthKey, i - 1)
                setXMLString(xmlFile, entryKey .. "#type", entry.typeKey)
                setXMLInt(xmlFile, entryKey .. "#day", entry.day)
                setXMLInt(xmlFile, entryKey .. "#hour", entry.hour)
                setXMLInt(xmlFile, entryKey .. "#minute", entry.minute)
                setXMLFloat(xmlFile, entryKey .. "#amount", entry.amount)
                setXMLInt(xmlFile, entryKey .. "#count", entry.count)
            end

            monthIndex = monthIndex + 1
        end

        farmIndex = farmIndex + 1
    end

    saveXMLFile(xmlFile)
    delete(xmlFile)
end

function MonthlyExpenseSheet.loadFromXMLFile()
    MonthlyExpenseSheet.farms = {}

    local filename = MonthlyExpenseSheet.getSavegameFilename()
    if filename == nil or not fileExists(filename) then
        return
    end

    local xmlFile = loadXMLFile("monthlyExpenseSheet", filename)
    if xmlFile == nil or xmlFile == 0 then
        log("Could not read %s", filename)
        return
    end

    local farmIndex = 0
    while true do
        local farmKey = string.format("monthlyExpenseSheet.farm(%d)", farmIndex)
        if not hasXMLProperty(xmlFile, farmKey) then
            break
        end

        local months = MonthlyExpenseSheet.getFarmMonths(getXMLInt(xmlFile, farmKey .. "#id") or 1)

        local monthIndex = 0
        while true do
            local monthKey = string.format("%s.month(%d)", farmKey, monthIndex)
            if not hasXMLProperty(xmlFile, monthKey) then
                break
            end

            local month = MonthlyExpenseSheet.getMonth(months, getXMLInt(xmlFile, monthKey .. "#year") or 1, getXMLInt(xmlFile, monthKey .. "#period") or 1)

            local typeIndex = 0
            while true do
                local typeKey = string.format("%s.type(%d)", monthKey, typeIndex)
                if not hasXMLProperty(xmlFile, typeKey) then
                    break
                end
                local moneyType = MonthlyExpenseSheet.getType(month, getXMLString(xmlFile, typeKey .. "#statistic") or "other",
                    getXMLString(xmlFile, typeKey .. "#title") or "", Utils.getNoNil(getXMLBool(xmlFile, typeKey .. "#isIncome"), false))
                moneyType.amount = getXMLFloat(xmlFile, typeKey .. "#amount") or 0
                moneyType.count = getXMLInt(xmlFile, typeKey .. "#count") or 0
                typeIndex = typeIndex + 1
            end

            local entryIndex = 0
            while true do
                local entryKey = string.format("%s.entry(%d)", monthKey, entryIndex)
                if not hasXMLProperty(xmlFile, entryKey) then
                    break
                end
                table.insert(month.entries, {
                    typeKey = getXMLString(xmlFile, entryKey .. "#type") or "other-",
                    day = getXMLInt(xmlFile, entryKey .. "#day") or 1,
                    hour = getXMLInt(xmlFile, entryKey .. "#hour") or 0,
                    minute = getXMLInt(xmlFile, entryKey .. "#minute") or 0,
                    amount = getXMLFloat(xmlFile, entryKey .. "#amount") or 0,
                    count = getXMLInt(xmlFile, entryKey .. "#count") or 1
                })
                entryIndex = entryIndex + 1
            end

            monthIndex = monthIndex + 1
        end

        farmIndex = farmIndex + 1
    end

    delete(xmlFile)
    log("Loaded records from %s", filename)
end

-- mod listener -----------------------------------------------------------------------------------------

function MonthlyExpenseSheet:loadMap(filename)
    if ExcessAnimalsSoldEvent ~= nil and ExcessAnimalsSoldEvent.run ~= nil then
        local superExcessRun = ExcessAnimalsSoldEvent.run
        ExcessAnimalsSoldEvent.run = function(event, ...)
            return MonthlyExpenseSheet.onAnimalSellRun(event, superExcessRun, ...)
        end
    end

    local hud = g_currentMission.hud
    if hud ~= nil and hud.showMoneyChange ~= nil then
        hud.showMoneyChange = Utils.prependedFunction(hud.showMoneyChange, MonthlyExpenseSheet.onShowMoneyChange)
    end
    if g_server ~= nil then
        MonthlyExpenseSheet.loadFromXMLFile()
    end
    MonthlyExpenseSheetDisplay.load()
end

function MonthlyExpenseSheet:deleteMap()
    MonthlyExpenseSheetDisplay.delete()
    MonthlyExpenseSheet.farms = {}
    MonthlyExpenseSheet.balances = {}
end

function MonthlyExpenseSheet:update(dt)
    if g_server ~= nil then
        MonthlyExpenseSheet.checkBalances(dt)
    end
    MonthlyExpenseSheetDisplay.update(dt)
end

function MonthlyExpenseSheet:draw()
    MonthlyExpenseSheetDisplay.draw()
end

function MonthlyExpenseSheet:mouseEvent(posX, posY, isDown, isUp, button)
    MonthlyExpenseSheetDisplay.mouseEvent(posX, posY, isDown, isUp, button)
end

FSBaseMission.addMoney = Utils.prependedFunction(FSBaseMission.addMoney, MonthlyExpenseSheet.onAddMoney)
local superIncomeHourChanged = PlaceableIncomePerHour.onHourChanged
PlaceableIncomePerHour.onHourChanged = function(placeable, ...)
    return MonthlyExpenseSheet.onIncomeHourChanged(placeable, superIncomeHourChanged, ...)
end
local superSellFillType = SellingStation.sellFillType
SellingStation.sellFillType = function(station, ...)
    return MonthlyExpenseSheet.onSellFillType(station, superSellFillType, ...)
end
MonthlyExpenseSheet.wrapProductionPoint()
if AnimalSellEvent ~= nil and AnimalSellEvent.run ~= nil then
    local superAnimalSellRun = AnimalSellEvent.run
    AnimalSellEvent.run = function(event, ...)
        return MonthlyExpenseSheet.onAnimalSellRun(event, superAnimalSellRun, ...)
    end
end
FSCareerMissionInfo.saveToXMLFile = Utils.appendedFunction(FSCareerMissionInfo.saveToXMLFile, MonthlyExpenseSheet.saveToXMLFile)

addModEventListener(MonthlyExpenseSheet)
