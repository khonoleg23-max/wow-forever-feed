-- KadgarGuide: подсказки Кадгара по прокачке и пояснения в подсказках к способностям.
local ADDON = ...
local KG = KadgarGuide
local P = "|cff69ccf0Кадгар:|r "
local db, char, cls

local function say(msg) DEFAULT_CHAT_FRAME:AddMessage(P .. msg) end
local function gold(s) return "|cffffd100" .. s .. "|r" end
local function fmt(s) return (s:gsub("%*%*(.-)%*%*", "|cffffd100%1|r")) end
local function norm(s) return (s:gsub("ё", "е"):gsub("Ё", "Е")) end
local function level() return UnitLevel("player") or 1 end

-- ---------- рекомендации ----------
local function zonesFor(lvl, n)
  local out = {}
  for _, z in ipairs(KG.zones) do
    if z[3] <= lvl + 1 and z[4] >= lvl + 2 and not char.zones[z[1]] then
      out[#out + 1] = z
      if #out >= (n or 3) then break end
    end
  end
  return out
end

local function dungeonsFor(lvl, n)
  local out = {}
  for _, d in ipairs(KG.dungeons) do
    if d[3] <= lvl + 1 and d[4] >= lvl + 1 and not char.dungeons[d[1]] then
      out[#out + 1] = d
      if #out >= (n or 3) then break end
    end
  end
  return out
end

local function list(items)
  local t = {}
  for _, x in ipairs(items) do t[#t + 1] = gold(x[2]) .. " (" .. x[3] .. "–" .. x[4] .. ", " .. x[5] .. ")" end
  return table.concat(t, "; ")
end

local function talentNow(lvl)
  local now, nxt
  for _, t in ipairs(KG.talents[cls] or {}) do
    if t[1] <= lvl then now = t elseif not nxt then nxt = t end
  end
  return now, nxt
end

local function skillsBetween(a, b)
  local t = {}
  for _, s in ipairs(KG.skills[cls] or {}) do
    if s[1] > a and s[1] <= b then t[#t + 1] = s[2] end
  end
  return t
end

local function showPlan()
  local lvl = level()
  say(gold(KG.className[cls] or "?") .. ", " .. lvl .. " ур. — что дальше:")
  local z = zonesFor(lvl)
  print("  |cff69ccf0Зоны:|r " .. (#z > 0 and list(z) or "все подходящие пройдены — бери подземелья и задания-наводки"))
  local d = dungeonsFor(lvl)
  if lvl < 13 then
    print("  |cff69ccf0Подземелья:|r с 13 ур. — Чертоги Танов под Стальгорном")
  elseif #d > 0 then
    print("  |cff69ccf0Подземелья:|r " .. list(d))
  end
  local now, nxt = talentNow(lvl)
  if lvl >= 10 and now then print("  |cff69ccf0Таланты:|r " .. fmt(now[2])) end
  if nxt then print("  |cff69ccf0С " .. nxt[1] .. " ур.:|r " .. fmt(nxt[2])) end
  local soon = {}
  for _, s in ipairs(KG.skills[cls] or {}) do
    if s[1] > lvl and s[1] <= lvl + 6 then soon[#soon + 1] = s[2] .. " (" .. s[1] .. ")" end
  end
  if #soon > 0 then print("  |cff69ccf0Скоро у тренера:|r " .. table.concat(soon, ", ")) end
end

-- ---------- события прокачки ----------
local function onLevelUp(lvl)
  if not db.hints then return end
  local lines = {}
  local new = skillsBetween(char.lastLevel or (lvl - 1), lvl)
  if #new > 0 then
    lines[#lines + 1] = "новое у тренера: " .. gold(table.concat(new, ", "))
  elseif lvl % 2 == 0 then
    lines[#lines + 1] = "загляни к тренеру — новые ранги"
  end
  for _, t in ipairs(KG.talents[cls] or {}) do
    if t[1] == lvl then lines[#lines + 1] = "таланты: " .. fmt(t[2]) end
  end
  for _, d in ipairs(KG.dungeons) do
    if d[3] == lvl and not char.dungeons[d[1]] then
      lines[#lines + 1] = "открылось подземелье " .. gold(d[2]) .. " (" .. d[5] .. ")"
    end
  end
  say("|cffffff00Уровень " .. lvl .. "!|r " .. (lines[1] or ""))
  for i = 2, #lines do print("  " .. lines[i]) end
  char.lastLevel = lvl
end

local function findZone(name)
  name = norm(name or "")
  for _, z in ipairs(KG.zones) do
    if norm(z[2]) == name then return z end
  end
end

local function findDungeon(name)
  name = norm(name or "")
  for _, d in ipairs(KG.dungeons) do
    if norm(d[2]) == name then return d end
  end
end

local function onZone()
  local inInst, itype = IsInInstance()
  if inInst and itype == "party" then
    local d = findDungeon((GetInstanceInfo()))
    if d and not char.inst then char.inst, char.instSince = d[1], time() end
    return
  end
  if char.inst then -- вышли из подземелья: долго были внутри — считаем пройденным
    local id, since = char.inst, char.instSince or time()
    char.inst, char.instSince = nil, nil
    if time() - since >= 900 and not char.dungeons[id] then
      char.dungeons[id] = true
      for _, d in ipairs(KG.dungeons) do
        if d[1] == id then say("отметил подземелье " .. gold(d[2]) .. " как пройденное.") end
      end
    end
  end
  if not db.hints then return end
  local lvl, z = level(), findZone(GetZoneText())
  if not z then return end
  local key = z[1] .. ":" .. lvl
  if char.warned[z[1]] == key then return end
  if lvl > z[4] + 1 then
    char.warned[z[1]] = key
    local better = zonesFor(lvl, 2)
    say("в «" .. z[2] .. "» опыта уже мало." .. (#better > 0 and (" Лучше: " .. list(better)) or ""))
  elseif lvl + 3 < z[3] then
    char.warned[z[1]] = key
    say("осторожно: «" .. z[2] .. "» — для " .. z[3] .. "–" .. z[4] .. " ур.")
  end
end

-- ---------- импорт из Discord ----------
local function import(code)
  local c, lo, hi, dl, zl = code:match("^[Kk][Qq]1:(%a+):(%d+):(%d+):([%dx%.]+):([%dx%.]+)$")
  if not c then say("не понял код. Пример: /kadgar KQ1:dru:20:24:4:5") return end
  if c ~= cls then
    say("этот код для героя-" .. (KG.className[c] or c) .. ", а ты " .. (KG.className[cls] or "?") .. ". Зайди нужным героем.")
    return
  end
  local nd, nz = 0, 0
  for id in dl:gmatch("%d+") do char.dungeons[tonumber(id)] = true; nd = nd + 1 end
  for id in zl:gmatch("%d+") do char.zones[tonumber(id)] = true; nz = nz + 1 end
  say("запомнил прогресс из Discord: подземелий " .. nd .. ", зон " .. nz .. ".")
  showPlan()
end

-- ---------- подсказки к способностям ----------
local function annotate(tt)
  if not tt or not db or db.tips == false or not tt.GetName or not tt.NumLines then return end
  local n = tt:GetName()
  local line = n and _G[n .. "TextLeft1"]
  local title = line and line:GetText()
  if not title then return end
  for i = 2, tt:NumLines() do -- уже добавлено (подсказку перерисовали несколько хуков)
    local l = _G[n .. "TextLeft" .. i]
    local t = l and l:GetText()
    if t and (t:find("^Кадгар: ") or t:find("^★ Советую")) then return end
  end
  local note = KG.notes[title]
  local rec = KG.rec[cls] and KG.rec[cls][title]
  local learn
  for _, s in ipairs(KG.skills[cls] or {}) do
    if s[2] == title then learn = s[1] break end
  end
  if not note and not rec then return end
  if note then tt:AddLine("Кадгар: " .. note, 0.41, 0.8, 0.94, true) end
  if rec then tt:AddLine("★ Советую в прокачке (с " .. rec .. " ур.)", 1, 0.82, 0, true) end
  if learn and learn > level() then tt:AddLine("У тренера с " .. learn .. " ур.", 0.7, 0.7, 0.7, true) end
  tt:Show()
end

local function hookTooltip(tt)
  if not tt or tt.kgHooked then return end
  tt.kgHooked = true
  tt:HookScript("OnShow", annotate)
  pcall(tt.HookScript, tt, "OnTooltipSetSpell", annotate)
  for _, m in ipairs({ "SetTalent", "SetSpellBookItem", "SetSpell", "SetSpellByID", "SetAction" }) do
    if tt[m] then hooksecurefunc(tt, m, annotate) end
  end
end

local function hookAll()
  hookTooltip(GameTooltip)
  if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall then
    pcall(TooltipDataProcessor.AddTooltipPostCall, TooltipDataProcessor.AllTypes, annotate)
  end
end

-- ---------- команды ----------
local function help()
  say("команды:")
  print("  /kadgar — куда идти, таланты, тренер")
  print("  /kadgar KQ1:… — вставить код из опроса в Discord")
  print("  /kadgar зона — отметить текущую зону пройденной")
  print("  /kadgar тихо — вкл/выкл подсказки в чате")
  print("  /kadgar пояснения — вкл/выкл пояснения в подсказках")
  print("  /kadgar сброс — забыть прогресс этого героя")
end

SLASH_KADGAR1, SLASH_KADGAR2, SLASH_KADGAR3 = "/kadgar", "/кадгар", "/kg"
SlashCmdList.KADGAR = function(msg)
  msg = (msg or ""):match("^%s*(.-)%s*$")
  local low = msg:lower()
  if msg == "" then showPlan()
  elseif low:match("^kq1:") then import(msg)
  elseif msg == "зона" or low == "zone" then
    local z = findZone(GetZoneText())
    if z then char.zones[z[1]] = true; say("«" .. z[2] .. "» отмечена пройденной.") else say("эту зону я не знаю.") end
  elseif msg == "тихо" or low == "quiet" then
    db.hints = not db.hints; say("подсказки в чате " .. (db.hints and "включены." or "выключены."))
  elseif msg == "пояснения" or low == "tips" then
    db.tips = not db.tips; say("пояснения в подсказках " .. (db.tips and "включены." or "выключены."))
  elseif msg == "сброс" or low == "reset" then
    char.zones, char.dungeons, char.warned = {}, {}, {}; say("прогресс героя забыт.")
  else help() end
end

-- ---------- запуск ----------
local f = CreateFrame("Frame")
f:RegisterEvent("ADDON_LOADED")
f:RegisterEvent("PLAYER_LOGIN")
f:RegisterEvent("PLAYER_LEVEL_UP")
f:RegisterEvent("ZONE_CHANGED_NEW_AREA")
f:RegisterEvent("PLAYER_ENTERING_WORLD")
f:SetScript("OnEvent", function(_, event, arg1)
  if event == "ADDON_LOADED" and arg1 == ADDON then
    KadgarGuideDB = KadgarGuideDB or {}
    db = KadgarGuideDB
    if db.hints == nil then db.hints = true end
    if db.tips == nil then db.tips = true end
    KadgarGuideChar = KadgarGuideChar or {}
    char = KadgarGuideChar
    char.zones, char.dungeons, char.warned = char.zones or {}, char.dungeons or {}, char.warned or {}
  elseif event == "PLAYER_LOGIN" then
    cls = KG.token[select(2, UnitClass("player"))]
    char.lastLevel = char.lastLevel or level()
    hookAll()
    if not char.greeted then
      char.greeted = true
      say("я с тобой. " .. gold("/kadgar") .. " — куда идти дальше; код из опроса в Discord тоже вставляй сюда.")
    end
  elseif event == "PLAYER_LEVEL_UP" then
    if cls then onLevelUp(arg1) end
  elseif cls and (event == "ZONE_CHANGED_NEW_AREA" or event == "PLAYER_ENTERING_WORLD") then
    onZone()
  end
end)
