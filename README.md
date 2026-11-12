# WoW Forever — русские ленты

Каждые 30 минут GitHub Actions забирает ленту Wowhead по WoW Forever, переводит заголовки и делает краткий пересказ на русском, а потом публикует две RSS-ленты через GitHub Pages:

- `docs/guides.xml` — гайды, хотфиксы, новости;
- `docs/professions.xml` — только профессии.

MonitoRSS читает эти ленты и выкладывает посты в Discord.

**Перевод.** Если в Settings → Secrets and variables → Actions добавлен секрет `ANTHROPIC_API_KEY`, перевод и пересказ делает Claude. Без секрета работает бесплатный онлайн-переводчик: он переводит заголовок и первые пару предложений.

Запустить вручную: вкладка Actions → «Translate WoW Forever feed» → Run workflow.
