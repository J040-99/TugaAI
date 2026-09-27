import sqlite3
import json

conn = sqlite3.connect(r'C:\TugaAI\TugaAI\backend\data\webui.db')
cur = conn.cursor()

# Ler estado atual
keys = (
    'direct.enable',
    'direct.integrations.enable',
    'ollama.enable',
    'ui.enable_signup',
    'openai.enable',
    'ui.name',
)
for key in keys:
    cur.execute('SELECT value FROM config WHERE key = ?', (key,))
    row = cur.fetchone()
    print(f'{key} = {row[0] if row else "(inexistente)"}')

# Atualizar para o produto TugaAI
updates = {
    'direct.enable': True,          # BYOK — cliente coloca a propria chave OpenRouter
    'direct.integrations.enable': False,
    'ollama.enable': False,         # sem modelos locais
    'ui.enable_signup': True,       # clientes podem registar-se
    'openai.enable': False,         # sem conexao global do servidor
}
for key, value in updates.items():
    cur.execute('SELECT value FROM config WHERE key = ?', (key,))
    if cur.fetchone():
        cur.execute(
            'UPDATE config SET value = ? WHERE key = ?',
            (json.dumps(value), key),
        )
    else:
        cur.execute(
            'INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)',
            (key, json.dumps(value), 0),
        )
    print(f'ATUALIZADO {key} = {json.dumps(value)}')

conn.commit()

# Confirmar
print('--- confirmacao ---')
for key in updates:
    cur.execute('SELECT value FROM config WHERE key = ?', (key,))
    row = cur.fetchone()
    print(f'{key} = {row[0]}')

conn.close()
