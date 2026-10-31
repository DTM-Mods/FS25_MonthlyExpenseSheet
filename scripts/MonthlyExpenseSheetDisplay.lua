-- Monthly Expense Sheet (PropaineX)
-- The sheet itself: drawn straight onto the screen (drawFilledRect + renderText) while open.
-- Left Alt + M (default) opens it. While open it has its own input context, so the keys don't drive
-- the vehicle or the player: Esc / Left Alt + M close, Q / E (MENU_PAGE_PREV/NEXT) change the month,
-- up / down select a category, left / right switch expenses / income. Mouse: click month tabs, the
-- EXPENSES / INCOME tabs and categories; the wheel scrolls the category list or the details.
-- Layout is in 1920 x 1080 reference pixels, top-left origin.

MonthlyExpenseSheetDisplay = {}
MonthlyExpenseSheetDisplay.INPUT_CONTEXT = "MES_SHEET"
MonthlyExpenseSheetDisplay.CLIENT_REFRESH_INTERVAL = 10000
MonthlyExpenseSheetDisplay.CATEGORY_ROWS = 14
MonthlyExpenseSheetDisplay.DETAIL_ROWS = 19
MonthlyExpenseSheetDisplay.NUM_MONTH_TABS = 6

local MOD_NAME = g_currentModName

local COLOR = {
    backdrop = {0, 0, 0, 0.55},
    panel = {0.086, 0.094, 0.086, 0.97},
    header = {0.486, 0.69, 0.125, 1},
    headerText = {0.08, 0.08, 0.08, 1},
    tab = {0.176, 0.188, 0.165, 1},
    rowHeader = {0.176, 0.188, 0.165, 1},
    rowStripe = {0.118, 0.129, 0.114, 1},
    rowSelected = {0.235, 0.314, 0.118, 1},
    detailsPanel = {0.125, 0.137, 0.122, 1},
    text = {0.92, 0.92, 0.9, 1},
    textDim = {0.59, 0.59, 0.57, 1},
    expense = {1, 0.59, 0.16, 1},
    income = {0.55, 0.78, 0.24, 1},
    up = {0.9, 0.35, 0.27, 1},
    keyBox = {0.92, 0.92, 0.9, 1}
}

local FALLBACK_MONTHS = {"March", "April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February"}

local function text(name, ...)
    local value = g_i18n:getText(name, MOD_NAME)
    if select("#", ...) > 0 then
        return string.format(value, ...)
    end
    return value
end

-- reference pixels -> screen
local function sx(px) return px / 1920 end
local function sy(py) return 1 - py / 1080 end
local function sh(px) return px / 1080 end

local function rect(x, y, w, h, color)
    drawFilledRect(sx(x), sy(y + h), sx(w), sh(h), color[1], color[2], color[3], color[4])
end

local function label(x, y, size, value, color, bold, alignment)
    setTextBold(bold == true)
    setTextAlignment(alignment or RenderText.ALIGN_LEFT)
    setTextColor(color[1], color[2], color[3], color[4])
    -- y = top of the text line
    renderText(sx(x), sy(y + size * 0.85), sh(size), value)
end

local function resetText()
    setTextBold(false)
    setTextAlignment(RenderText.ALIGN_LEFT)
    setTextColor(1, 1, 1, 1)
end

local function isInside(posX, posY, x, y, w, h)
    return posX >= sx(x) and posX <= sx(x + w) and posY <= sy(y) and posY >= sy(y + h)
end

function MonthlyExpenseSheetDisplay.getMonthName(period, short)
    local ok, name = pcall(g_i18n.formatPeriod, g_i18n, period, short)
    if not ok or type(name) ~= "string" or name == "" then
        name = FALLBACK_MONTHS[period] or "?"
        if short then
            name = name:sub(1, 3)
        end
    end
    return name
end

function MonthlyExpenseSheetDisplay.formatMoney(amount)
    local value = math.floor(math.abs(amount) + 0.5)
    local ok, result = pcall(g_i18n.formatMoney, g_i18n, value, 0, true, true)
    if ok and type(result) == "string" then
        return result
    end

    local digits = tostring(value):reverse():gsub("(%d%d%d)", "%1,"):reverse():gsub("^,", "")
    return digits .. " $"
end

local function signedMoney(amount)
    return (amount < 0 and "- " or "+ ") .. MonthlyExpenseSheetDisplay.formatMoney(amount)
end

-- state ------------------------------------------------------------------------------------------------

local state = {
    isOpen = false,
    eventIds = {},
    months = nil,           -- client copy (multiplayer)
    isWaiting = false,
    refreshTimer = 0,
    monthKey = nil,         -- selected month
    showIncome = false,
    selected = 1,
    categoryScroll = 0,
    detailScroll = 0
}

function MonthlyExpenseSheetDisplay.load()
    state.isOpen = false
    state.months = nil
end

function MonthlyExpenseSheetDisplay.delete()
    if state.isOpen then
        MonthlyExpenseSheetDisplay.close()
    end
end

function MonthlyExpenseSheetDisplay.getFarmId()
    return g_currentMission:getFarmId()
end

function MonthlyExpenseSheetDisplay.getMonths()
    if g_server ~= nil then
        return MonthlyExpenseSheet.farms[MonthlyExpenseSheetDisplay.getFarmId()] or {}
    end
    return state.months or {}
end

function MonthlyExpenseSheetDisplay.getSortedMonthKeys()
    local keys = {}
    for monthKey in pairs(MonthlyExpenseSheetDisplay.getMonths()) do
        table.insert(keys, monthKey)
    end
    table.sort(keys)
    return keys
end

function MonthlyExpenseSheetDisplay.getPreviousMonthKey(monthKey)
    local year, period = math.floor(monthKey / 100), monthKey % 100
    if period == 1 then
        return MonthlyExpenseSheet.getMonthKey(year - 1, 12)
    end
    return MonthlyExpenseSheet.getMonthKey(year, period - 1)
end

-- categories of the selected side, biggest first
function MonthlyExpenseSheetDisplay.getCategories(month, showIncome)
    local list = {}
    if month ~= nil then
        for _, moneyType in pairs(month.types) do
            if moneyType.isIncome == showIncome then
                table.insert(list, moneyType)
            end
        end
    end
    table.sort(list, function(a, b)
        if math.abs(a.amount) == math.abs(b.amount) then
            return a.key < b.key
        end
        return math.abs(a.amount) > math.abs(b.amount)
    end)
    return list
end

function MonthlyExpenseSheetDisplay.getTotals(month)
    local expenses, income = 0, 0
    if month ~= nil then
        for _, moneyType in pairs(month.types) do
            if moneyType.isIncome then
                income = income + moneyType.amount
            else
                expenses = expenses + moneyType.amount
            end
        end
    end
    return expenses, income
end

-- open / close + input -------------------------------------------------------------------------------

function MonthlyExpenseSheetDisplay.toggle()
    if state.isOpen then
        MonthlyExpenseSheetDisplay.close()
    else
        MonthlyExpenseSheetDisplay.open()
    end
end

function MonthlyExpenseSheetDisplay.open()
    if state.isOpen or g_gui:getIsGuiVisible() then
        return
    end

    local environment = g_currentMission.environment
    state.monthKey = MonthlyExpenseSheet.getMonthKey(environment.currentYear or 1, environment.currentPeriod or 1)
    state.showIncome = false
    state.selected = 1
    state.categoryScroll = 0
    state.detailScroll = 0
    state.isOpen = true

    if g_server == nil then
        MonthlyExpenseSheetDisplay.requestData()
    end

    g_inputBinding:setContext(MonthlyExpenseSheetDisplay.INPUT_CONTEXT, true, false)
    state.eventIds = {}
    local function register(action, callback)
        if action ~= nil then
            local _, eventId = g_inputBinding:registerActionEvent(action, MonthlyExpenseSheetDisplay, callback, false, true, false, true)
            if eventId ~= nil then
                g_inputBinding:setActionEventTextVisibility(eventId, false)
                table.insert(state.eventIds, eventId)
            end
        end
    end
    register(InputAction.MENU_BACK, MonthlyExpenseSheetDisplay.close)
    register(InputAction.MES_TOGGLE_SHEET, MonthlyExpenseSheetDisplay.close)
    register(InputAction.MENU_PAGE_PREV, function() MonthlyExpenseSheetDisplay.changeMonth(-1) end)
    register(InputAction.MENU_PAGE_NEXT, function() MonthlyExpenseSheetDisplay.changeMonth(1) end)
    register(InputAction.MENU_AXIS_UP_DOWN, function(_, _, value)
        MonthlyExpenseSheetDisplay.changeSelection(value > 0 and -1 or 1)
    end)
    register(InputAction.MENU_AXIS_LEFT_RIGHT, function(_, _, value)
        MonthlyExpenseSheetDisplay.setShowIncome(value > 0)
    end)

    g_inputBinding:setShowMouseCursor(true)
end

function MonthlyExpenseSheetDisplay.close()
    if not state.isOpen then
        return
    end
    state.isOpen = false

    g_inputBinding:revertContext(true)
    g_inputBinding:setShowMouseCursor(false)
    state.eventIds = {}
end

function MonthlyExpenseSheetDisplay.requestData()
    state.isWaiting = true
    state.refreshTimer = MonthlyExpenseSheetDisplay.CLIENT_REFRESH_INTERVAL
    g_client:getServerConnection():sendEvent(MESRequestEvent.new(MonthlyExpenseSheetDisplay.getFarmId()))
end

function MonthlyExpenseSheetDisplay.onDataReceived(farmId, months)
    if farmId == MonthlyExpenseSheetDisplay.getFarmId() then
        state.months = months
        state.isWaiting = false
    end
end

function MonthlyExpenseSheetDisplay.changeMonth(direction)
    local keys = MonthlyExpenseSheetDisplay.getSortedMonthKeys()
    if #keys == 0 then
        return
    end

    local index = nil
    for i, monthKey in ipairs(keys) do
        if monthKey == state.monthKey then
            index = i
        end
    end
    -- the current month may have no records yet; step from where it would be
    if index == nil then
        index = direction < 0 and #keys + 1 or 0
        for i, monthKey in ipairs(keys) do
            if monthKey > state.monthKey then
                index = direction < 0 and i or i - 1
                break
            end
        end
    end

    index = math.max(1, math.min(#keys, index + direction))
    if keys[index] ~= state.monthKey then
        state.monthKey = keys[index]
        state.selected = 1
        state.categoryScroll = 0
        state.detailScroll = 0
    end
end

function MonthlyExpenseSheetDisplay.setShowIncome(showIncome)
    if state.showIncome ~= showIncome then
        state.showIncome = showIncome
        state.selected = 1
        state.categoryScroll = 0
        state.detailScroll = 0
    end
end

function MonthlyExpenseSheetDisplay.changeSelection(direction)
    local month = MonthlyExpenseSheetDisplay.getMonths()[state.monthKey]
    local count = #MonthlyExpenseSheetDisplay.getCategories(month, state.showIncome)
    if count == 0 then
        return
    end

    state.selected = math.max(1, math.min(count, state.selected + direction))
    state.detailScroll = 0

    local rows = MonthlyExpenseSheetDisplay.CATEGORY_ROWS
    if state.selected > state.categoryScroll + rows then
        state.categoryScroll = state.selected - rows
    elseif state.selected <= state.categoryScroll then
        state.categoryScroll = state.selected - 1
    end
end

function MonthlyExpenseSheetDisplay.update(dt)
    if not state.isOpen then
        return
    end

    if g_gui:getIsGuiVisible() then
        MonthlyExpenseSheetDisplay.close()
        return
    end

    if g_server == nil then
        state.refreshTimer = state.refreshTimer - dt
        if state.refreshTimer <= 0 then
            MonthlyExpenseSheetDisplay.requestData()
        end
    end
end

-- clickable areas, filled while drawing
local hitAreas = {}

function MonthlyExpenseSheetDisplay.mouseEvent(posX, posY, isDown, isUp, button)
    if not state.isOpen then
        return
    end

    if isDown and (button == Input.MOUSE_BUTTON_WHEEL_UP or button == Input.MOUSE_BUTTON_WHEEL_DOWN) then
        local direction = button == Input.MOUSE_BUTTON_WHEEL_UP and -1 or 1
        local details = hitAreas.details
        if details ~= nil and isInside(posX, posY, details[1], details[2], details[3], details[4]) then
            state.detailScroll = math.max(0, math.min(hitAreas.maxDetailScroll or 0, state.detailScroll + direction * 3))
        else
            MonthlyExpenseSheetDisplay.changeSelection(direction)
        end
        return
    end

    if isDown and button == Input.MOUSE_BUTTON_LEFT then
        for _, area in ipairs(hitAreas) do
            if isInside(posX, posY, area.x, area.y, area.w, area.h) then
                area.onClick()
                return
            end
        end
    end
end

-- drawing ----------------------------------------------------------------------------------------------

local PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 160, 90, 1600, 900
local LEFT_X = PANEL_X + 25
local LEFT_W = 900
local RIGHT_X = PANEL_X + 950
local RIGHT_W = PANEL_W - 975

function MonthlyExpenseSheetDisplay.draw()
    if not state.isOpen then
        return
    end

    hitAreas = {}
    local months = MonthlyExpenseSheetDisplay.getMonths()
    local month = months[state.monthKey]
    local year, period = math.floor(state.monthKey / 100), state.monthKey % 100

    rect(0, 0, 1920, 1080, COLOR.backdrop)
    rect(PANEL_X, PANEL_Y, PANEL_W, PANEL_H, COLOR.panel)

    -- header
    rect(PANEL_X, PANEL_Y, PANEL_W, 60, COLOR.header)
    label(PANEL_X + 25, PANEL_Y + 14, 30, text("mes_title"), COLOR.headerText, true)
    local farm = g_farmManager:getFarmById(MonthlyExpenseSheetDisplay.getFarmId())
    local farmName = farm ~= nil and farm.name or ""
    label(PANEL_X + PANEL_W - 25, PANEL_Y + 18, 22, farmName .. "   |   " .. text("mes_year", year), COLOR.headerText, true, RenderText.ALIGN_RIGHT)

    MonthlyExpenseSheetDisplay.drawMonthTabs(months)

    -- month heading + EXPENSES / INCOME tabs
    local y = PANEL_Y + 140
    label(LEFT_X, y, 24, string.upper(MonthlyExpenseSheetDisplay.getMonthName(period, false)) .. "  -  " .. text("mes_year", year), COLOR.text, true)
    MonthlyExpenseSheetDisplay.drawSideTab(LEFT_X + LEFT_W - 330, y - 4, false)
    MonthlyExpenseSheetDisplay.drawSideTab(LEFT_X + LEFT_W - 160, y - 4, true)

    local categories = MonthlyExpenseSheetDisplay.getCategories(month, state.showIncome)
    if state.selected > #categories then
        state.selected = math.max(1, #categories)
    end
    MonthlyExpenseSheetDisplay.drawCategories(months, categories, y + 45)
    MonthlyExpenseSheetDisplay.drawTotals(month)
    MonthlyExpenseSheetDisplay.drawDetails(month, categories[state.selected])
    MonthlyExpenseSheetDisplay.drawKeyHints()

    if g_server == nil and state.isWaiting and state.months == nil then
        label(PANEL_X + PANEL_W / 2, PANEL_Y + PANEL_H / 2, 24, text("mes_loading"), COLOR.textDim, true, RenderText.ALIGN_CENTER)
    end

    resetText()
end

function MonthlyExpenseSheetDisplay.drawMonthTabs(months)
    -- tabs = recorded months plus the selected one, the selected tab kept in view
    local keys = MonthlyExpenseSheetDisplay.getSortedMonthKeys()
    local hasSelected = false
    for _, monthKey in ipairs(keys) do
        hasSelected = hasSelected or monthKey == state.monthKey
    end
    if not hasSelected then
        table.insert(keys, state.monthKey)
        table.sort(keys)
    end

    local selectedIndex = 1
    for i, monthKey in ipairs(keys) do
        if monthKey == state.monthKey then
            selectedIndex = i
        end
    end
    local numTabs = MonthlyExpenseSheetDisplay.NUM_MONTH_TABS
    local first = math.max(1, math.min(selectedIndex - numTabs + 1 + math.floor(numTabs / 2), #keys - numTabs + 1))
    first = math.max(1, math.min(first, selectedIndex))

    local x, y = LEFT_X, PANEL_Y + 78
    label(x, y + 4, 28, "<", first > 1 and COLOR.text or COLOR.textDim, true)
    table.insert(hitAreas, {x = x - 5, y = y, w = 30, h = 40, onClick = function() MonthlyExpenseSheetDisplay.changeMonth(-1) end})
    x = x + 40

    for i = first, math.min(#keys, first + numTabs - 1) do
        local monthKey = keys[i]
        local isSelected = monthKey == state.monthKey
        rect(x, y, 100, 40, isSelected and COLOR.header or COLOR.tab)
        label(x + 50, y + 7, 22, string.upper(MonthlyExpenseSheetDisplay.getMonthName(monthKey % 100, true)), isSelected and COLOR.headerText or COLOR.text, true, RenderText.ALIGN_CENTER)
        table.insert(hitAreas, {x = x, y = y, w = 100, h = 40, onClick = function()
            state.monthKey = monthKey
            state.selected = 1
            state.categoryScroll = 0
            state.detailScroll = 0
        end})
        x = x + 110
    end

    label(x, y + 4, 28, ">", first + numTabs - 1 < #keys and COLOR.text or COLOR.textDim, true)
    table.insert(hitAreas, {x = x - 5, y = y, w = 30, h = 40, onClick = function() MonthlyExpenseSheetDisplay.changeMonth(1) end})
end

function MonthlyExpenseSheetDisplay.drawSideTab(x, y, isIncome)
    local isSelected = state.showIncome == isIncome
    rect(x, y, 150, 34, isSelected and COLOR.header or COLOR.tab)
    label(x + 75, y + 6, 20, text(isIncome and "mes_income" or "mes_expenses"), isSelected and COLOR.headerText or COLOR.text, true, RenderText.ALIGN_CENTER)
    table.insert(hitAreas, {x = x, y = y, w = 150, h = 34, onClick = function() MonthlyExpenseSheetDisplay.setShowIncome(isIncome) end})
end

function MonthlyExpenseSheetDisplay.drawCategories(months, categories, y)
    local previousMonth = months[MonthlyExpenseSheetDisplay.getPreviousMonthKey(state.monthKey)]
    local amountColor = state.showIncome and COLOR.income or COLOR.expense

    rect(LEFT_X - 10, y - 5, LEFT_W, 35, COLOR.rowHeader)
    label(LEFT_X, y, 18, text("mes_category"), COLOR.textDim, true)
    label(LEFT_X + 470, y, 18, text("mes_charges"), COLOR.textDim, true, RenderText.ALIGN_RIGHT)
    label(LEFT_X + 690, y, 18, text("mes_amount"), COLOR.textDim, true, RenderText.ALIGN_RIGHT)
    label(LEFT_X + 840, y, 18, text("mes_lastMonth"), COLOR.textDim, true, RenderText.ALIGN_RIGHT)
    y = y + 40

    if #categories == 0 then
        local key = next(months) == nil and "mes_noMonths" or "mes_noEntries"
        label(LEFT_X, y + 6, 20, text(key), COLOR.textDim, false)
        return
    end

    local rows = MonthlyExpenseSheetDisplay.CATEGORY_ROWS
    local listY = y
    for i = state.categoryScroll + 1, math.min(#categories, state.categoryScroll + rows) do
        local moneyType = categories[i]
        local isSelected = i == state.selected

        if isSelected then
            rect(LEFT_X - 10, y - 4, LEFT_W, 28, COLOR.rowSelected)
        elseif i % 2 == 0 then
            rect(LEFT_X - 10, y - 4, LEFT_W, 28, COLOR.rowStripe)
        end

        label(LEFT_X, y, 18, MonthlyExpenseSheet.getTypeName(moneyType), COLOR.text, isSelected)
        label(LEFT_X + 470, y, 18, tostring(moneyType.count), COLOR.textDim, false, RenderText.ALIGN_RIGHT)
        label(LEFT_X + 690, y, 18, signedMoney(moneyType.amount), amountColor, true, RenderText.ALIGN_RIGHT)

        local lastAmount = 0
        if previousMonth ~= nil and previousMonth.types[moneyType.key] ~= nil then
            lastAmount = previousMonth.types[moneyType.key].amount
        end
        label(LEFT_X + 840, y, 18, MonthlyExpenseSheetDisplay.formatMoney(lastAmount), COLOR.textDim, false, RenderText.ALIGN_RIGHT)

        -- up = more money than last month; red when that's a bigger expense, green when it's more income
        local difference = math.abs(moneyType.amount) - math.abs(lastAmount)
        if math.abs(difference) < 0.5 then
            label(LEFT_X + 868, y, 16, "=", COLOR.textDim, false, RenderText.ALIGN_CENTER)
        else
            local isGood = (difference > 0) == state.showIncome
            MonthlyExpenseSheetDisplay.drawArrow(LEFT_X + 868, y + 10, difference > 0, isGood and COLOR.income or COLOR.up)
        end

        local index = i
        table.insert(hitAreas, {x = LEFT_X - 10, y = y - 4, w = LEFT_W, h = 28, onClick = function()
            state.selected = index
            state.detailScroll = 0
        end})

        y = y + 29
    end

    -- scroll bar when not every category fits
    if #categories > rows then
        local barH = rows * 29 - 4
        local thumbH = math.max(30, barH * rows / #categories)
        local thumbY = listY - 4 + (barH - thumbH) * state.categoryScroll / (#categories - rows)
        rect(LEFT_X + LEFT_W - 16, listY - 4, 4, barH, COLOR.rowStripe)
        rect(LEFT_X + LEFT_W - 16, thumbY, 4, thumbH, COLOR.header)
    end
end

-- small triangle from stacked bars (the game font has no arrow signs)
function MonthlyExpenseSheetDisplay.drawArrow(centerX, centerY, isUp, color)
    for i = 0, 6 do
        local width = isUp and (2 + i * 2) or (14 - i * 2)
        rect(centerX - width / 2, centerY - 7 + i * 2, width, 2, color)
    end
end

function MonthlyExpenseSheetDisplay.drawTotals(month)
    local expenses, income = MonthlyExpenseSheetDisplay.getTotals(month)
    local net = expenses + income

    local y = PANEL_Y + 650
    rect(LEFT_X - 10, y, LEFT_W, 2, COLOR.header)
    y = y + 14
    label(LEFT_X, y, 22, text("mes_totalExpenses"), COLOR.text, true)
    label(LEFT_X + 690, y, 22, signedMoney(expenses), COLOR.expense, true, RenderText.ALIGN_RIGHT)
    y = y + 36
    label(LEFT_X, y, 22, text("mes_totalIncome"), COLOR.text, true)
    label(LEFT_X + 690, y, 22, signedMoney(income), COLOR.income, true, RenderText.ALIGN_RIGHT)
    y = y + 36
    label(LEFT_X, y, 22, text("mes_net"), COLOR.text, true)
    label(LEFT_X + 690, y, 22, signedMoney(net), net < 0 and COLOR.up or COLOR.income, true, RenderText.ALIGN_RIGHT)
end

function MonthlyExpenseSheetDisplay.drawDetails(month, moneyType)
    local x, y, w, h = RIGHT_X, PANEL_Y + 135, RIGHT_W, 665
    rect(x, y, w, h, COLOR.detailsPanel)
    rect(x, y, w, 40, COLOR.rowHeader)
    hitAreas.details = {x, y, w, h}

    if moneyType == nil then
        return
    end

    label(x + 15, y + 8, 22, text("mes_details", MonthlyExpenseSheet.getTypeName(moneyType)), COLOR.header, true)
    label(x + 15, y + 52, 17, text("mes_dateTime"), COLOR.textDim, true)
    label(x + w - 15, y + 52, 17, text("mes_amount"), COLOR.textDim, true, RenderText.ALIGN_RIGHT)

    -- newest first
    local entries = {}
    for i = #month.entries, 1, -1 do
        if month.entries[i].typeKey == moneyType.key then
            table.insert(entries, month.entries[i])
        end
    end

    local rows = MonthlyExpenseSheetDisplay.DETAIL_ROWS
    hitAreas.maxDetailScroll = math.max(0, #entries - rows)
    state.detailScroll = math.min(state.detailScroll, hitAreas.maxDetailScroll)

    local monthName = MonthlyExpenseSheetDisplay.getMonthName(month.period, true)
    local amountColor = moneyType.isIncome and COLOR.income or COLOR.expense
    local rowY = y + 84
    for i = state.detailScroll + 1, math.min(#entries, state.detailScroll + rows) do
        local entry = entries[i]
        local when = string.format("%s %d   %02d:%02d", monthName, entry.day, entry.hour, entry.minute)
        if entry.count > 1 then
            when = when .. string.format("   (x%d)", entry.count)
        end
        label(x + 15, rowY, 18, when, COLOR.text, false)
        label(x + w - 15, rowY, 18, signedMoney(entry.amount), amountColor, false, RenderText.ALIGN_RIGHT)
        rowY = rowY + 29
    end

    if hitAreas.maxDetailScroll > 0 then
        -- scroll bar
        local barH = h - 90
        local thumbH = math.max(30, barH * rows / #entries)
        local thumbY = y + 84 + (barH - thumbH) * state.detailScroll / hitAreas.maxDetailScroll
        rect(x + w - 6, y + 84, 4, barH, COLOR.rowStripe)
        rect(x + w - 6, thumbY, 4, thumbH, COLOR.header)
    end
end

function MonthlyExpenseSheetDisplay.drawKeyHints()
    local x, y = LEFT_X, PANEL_Y + PANEL_H - 55
    local hints = {
        {"ESC", text("mes_keyClose")},
        {"Q / E", text("mes_keyMonth")},
        {"UP / DOWN", text("mes_keySelect")},
        {"LEFT / RIGHT", text("mes_keySide")}
    }

    for _, hint in ipairs(hints) do
        setTextBold(true)
        local keyWidth = getTextWidth(sh(18), hint[1]) * 1920
        rect(x, y, keyWidth + 20, 30, COLOR.keyBox)
        label(x + 10, y + 5, 18, hint[1], COLOR.headerText, true)
        x = x + keyWidth + 30
        setTextBold(false)
        label(x, y + 5, 18, hint[2], COLOR.text, false)
        x = x + getTextWidth(sh(18), hint[2]) * 1920 + 35
    end
end

-- Left Alt + M, on foot and in vehicles
PlayerInputComponent.registerGlobalPlayerActionEvents = Utils.appendedFunction(PlayerInputComponent.registerGlobalPlayerActionEvents, function(self)
    local _, eventId = g_inputBinding:registerActionEvent(InputAction.MES_TOGGLE_SHEET, MonthlyExpenseSheetDisplay, MonthlyExpenseSheetDisplay.toggle, false, true, false, true)
    if eventId ~= nil then
        g_inputBinding:setActionEventTextVisibility(eventId, false)
    end
end)
