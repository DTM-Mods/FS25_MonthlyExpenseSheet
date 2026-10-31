-- Monthly Expense Sheet (PropaineX)
-- Multiplayer: the records live on the server. A client opening the sheet sends MESRequestEvent with its
-- farm; the server answers that connection only with MESDataEvent, holding all of that farm's months.

MESRequestEvent = {}
local MESRequestEvent_mt = Class(MESRequestEvent, Event)
InitEventClass(MESRequestEvent, "MESRequestEvent")

function MESRequestEvent.emptyNew()
    return Event.new(MESRequestEvent_mt)
end

function MESRequestEvent.new(farmId)
    local self = MESRequestEvent.emptyNew()
    self.farmId = farmId
    return self
end

function MESRequestEvent:writeStream(streamId, connection)
    streamWriteUIntN(streamId, self.farmId, FarmManager.FARM_ID_SEND_NUM_BITS)
end

function MESRequestEvent:readStream(streamId, connection)
    self.farmId = streamReadUIntN(streamId, FarmManager.FARM_ID_SEND_NUM_BITS)
    self:run(connection)
end

function MESRequestEvent:run(connection)
    if connection:getIsServer() then
        return
    end

    -- only the requesting player's own farm
    local userId = g_currentMission.userManager:getUserIdByConnection(connection)
    local farm = g_farmManager:getFarmByUserId(userId)
    if farm == nil or farm.farmId ~= self.farmId then
        return
    end

    connection:sendEvent(MESDataEvent.new(self.farmId, MonthlyExpenseSheet.farms[self.farmId] or {}))
end


MESDataEvent = {}
local MESDataEvent_mt = Class(MESDataEvent, Event)
InitEventClass(MESDataEvent, "MESDataEvent")

function MESDataEvent.emptyNew()
    return Event.new(MESDataEvent_mt)
end

function MESDataEvent.new(farmId, months)
    local self = MESDataEvent.emptyNew()
    self.farmId = farmId
    self.months = months
    return self
end

function MESDataEvent:writeStream(streamId, connection)
    streamWriteUIntN(streamId, self.farmId, FarmManager.FARM_ID_SEND_NUM_BITS)

    local monthList = {}
    for _, month in pairs(self.months) do
        table.insert(monthList, month)
    end
    streamWriteUInt16(streamId, #monthList)

    for _, month in ipairs(monthList) do
        streamWriteUInt16(streamId, month.year)
        streamWriteUInt8(streamId, month.period)

        -- types are sent once; entries point at them by index
        local typeList, typeIndex = {}, {}
        for typeKey, moneyType in pairs(month.types) do
            table.insert(typeList, moneyType)
            typeIndex[typeKey] = #typeList
        end

        streamWriteUInt16(streamId, #typeList)
        for _, moneyType in ipairs(typeList) do
            streamWriteString(streamId, moneyType.statistic)
            streamWriteString(streamId, moneyType.title)
            streamWriteBool(streamId, moneyType.isIncome)
            streamWriteFloat32(streamId, moneyType.amount)
            streamWriteInt32(streamId, moneyType.count)
        end

        local entries = {}
        for _, entry in ipairs(month.entries) do
            if typeIndex[entry.typeKey] ~= nil then
                table.insert(entries, entry)
            end
        end

        streamWriteUInt16(streamId, #entries)
        for _, entry in ipairs(entries) do
            streamWriteUInt16(streamId, typeIndex[entry.typeKey])
            streamWriteUInt8(streamId, entry.day)
            streamWriteUInt8(streamId, entry.hour)
            streamWriteUInt8(streamId, entry.minute)
            streamWriteFloat32(streamId, entry.amount)
            streamWriteInt32(streamId, entry.count)
        end
    end
end

function MESDataEvent:readStream(streamId, connection)
    self.farmId = streamReadUIntN(streamId, FarmManager.FARM_ID_SEND_NUM_BITS)
    self.months = {}

    local numMonths = streamReadUInt16(streamId)
    for _ = 1, numMonths do
        local year = streamReadUInt16(streamId)
        local period = streamReadUInt8(streamId)
        local month = {year = year, period = period, types = {}, entries = {}}
        self.months[MonthlyExpenseSheet.getMonthKey(year, period)] = month

        local typeList = {}
        local numTypes = streamReadUInt16(streamId)
        for _ = 1, numTypes do
            local statistic = streamReadString(streamId)
            local title = streamReadString(streamId)
            local isIncome = streamReadBool(streamId)
            local moneyType = MonthlyExpenseSheet.getType(month, statistic, title, isIncome)
            moneyType.amount = streamReadFloat32(streamId)
            moneyType.count = streamReadInt32(streamId)
            table.insert(typeList, moneyType)
        end

        local numEntries = streamReadUInt16(streamId)
        for _ = 1, numEntries do
            local moneyType = typeList[streamReadUInt16(streamId)]
            local entry = {
                day = streamReadUInt8(streamId),
                hour = streamReadUInt8(streamId),
                minute = streamReadUInt8(streamId),
                amount = streamReadFloat32(streamId),
                count = streamReadInt32(streamId)
            }
            if moneyType ~= nil then
                entry.typeKey = moneyType.key
                table.insert(month.entries, entry)
            end
        end
    end

    self:run(connection)
end

function MESDataEvent:run(connection)
    if connection:getIsServer() then
        MonthlyExpenseSheetDisplay.onDataReceived(self.farmId, self.months)
    end
end
