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

    local year, period, day, hour, minute = MonthlyExpenseSheet.getNow()
    MonthlyExpenseSheet.record(farmId, amount, statistic, title, year, period, day, hour, minute)

    local balance = MonthlyExpenseSheet.balances[farmId]
    if balance ~= nil then
        balance.recorded = balance.recorded + amount
    end
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

-- text for a category; the money type's own l10n title when there is one
function MonthlyExpenseSheet.getTypeName(moneyType)
    local statistic = moneyType.statistic or ""
    if statistic == MonthlyExpenseSheet.UNTRACKED then
        return g_i18n:getText("mes_untracked", MonthlyExpenseSheet.MOD_NAME)
    end

    -- the l10n key the popup uses; mods sometimes give plain text instead
    local title = moneyType.title
    if title ~= nil and title ~= "" then
        if g_i18n:hasText(title) then
            return g_i18n:getText(title)
        end
        if not title:find("^finance_") then
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
FSCareerMissionInfo.saveToXMLFile = Utils.appendedFunction(FSCareerMissionInfo.saveToXMLFile, MonthlyExpenseSheet.saveToXMLFile)

addModEventListener(MonthlyExpenseSheet)
