import re

with open('d:/The App/ONE/templates/index.html', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Meta tag
code = re.sub(r' and Gemini AI powerup', '', code)

# 2. CSS blocks related to gemini
code = re.sub(r'(?s)/\*\s*gemini panel accent\s*\*/.*?\/\*\s*── GEMINI ACTION BUTTON ──\s*\*/.*?} \n', '', code)
code = re.sub(r'\.gemini-btn:disabled \{ opacity: 0\.45; cursor: not-allowed; \}\n', '', code)

# 3. HTML pills
code = re.sub(r'<button class="nav-pill" id="pill-gemini" onclick="switchPanel\(\'gemini\', this\)">Gemini ⚡</button>\n', '', code)

# 4. Upscale panel Gemini Suggestions
code = re.sub(r'(?s)<label class="check-item">\s*<input type="checkbox" id="expand-gemini-guide" checked>\s*<span>Gemini Suggestions</span>\s*</label>\n', '', code)

# 5. Gemini Tool Panel
code = re.sub(r'(?s)<!-- PANEL: GEMINI POWERUP -->\s*<div class="tool-panel" id="panel-gemini">.*?</div>\s*</div>\s*<!-- ── EXPAND INFO BAR ── -->', '<!-- ── EXPAND INFO BAR ── -->', code)

# 6. JavaScript logic for Gemini
code = re.sub(r'const expandGem = document\.getElementById\(\'expand-gemini-guide\'\);\n\s*formData\.append\(\'gemini_guide\', expandGem\.checked \? \'true\' : \'false\'\);\n', '', code)

gemini_js = r'(?s)// ── GEMINI POWERUP ──.*?// ── SHUTDOWN SCREEN ──'
code = re.sub(gemini_js, '// ── SHUTDOWN SCREEN ──', code)

with open('d:/The App/ONE/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(code)
