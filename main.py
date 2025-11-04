# main.py
import os
import threading
import discord
from discord.ext import tasks
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
import time
from flask import Flask
from dotenv import load_dotenv

# ============= FLASK (PARA RENDER) =============
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot está online! Verificando preço a cada 30 min.", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000, use_reloader=False)

# ============= DISCORD BOT =============
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
ITEM_NAME_RAW = "★ Nomad Knife | Urban Masked (Field-Tested)"
APPID = 730
CURRENCY = 7
MAX_PRICE = 900.0

ITEM_NAME = urllib.parse.quote(ITEM_NAME_RAW)
PRICE_URL = "https://steamcommunity.com/market/priceoverview/"
LISTINGS_URL = f"https://steamcommunity.com/market/listings/{APPID}/{ITEM_NAME}"
CSGOFLOAT_API = "https://api.csgofloat.com/"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/html',
    'Referer': 'https://steamcommunity.com/market/',
})

last_float_success = 0

def get_price():
    params = {'appid': APPID, 'currency': CURRENCY, 'market_hash_name': ITEM_NAME_RAW}
    try:
        time.sleep(1.5)
        resp = session.get(PRICE_URL, params=params, timeout=10).json()
        if resp.get('success'):
            price_str = resp['lowest_price'].replace('R$', '').replace('.', '').replace(',', '.').strip()
            return float(price_str), resp.get('volume', '0')
    except Exception as e:
        print(f"[ERRO Preço]: {e}")
    return None, None

def get_float_csgofloat(inspect_link):
    try:
        time.sleep(1.2)
        resp = session.get(CSGOFLOAT_API, params={'url': inspect_link}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return round(data['iteminfo']['paintwear'], 6)
    except Exception as e:
        print(f"[ERRO Float API]: {e}")
    return None

def get_listings_with_float():
    global last_float_success
    if time.time() - last_float_success < 600:
        return None

    try:
        time.sleep(2)
        resp = session.get(LISTINGS_URL, timeout=15)
        if resp.status_code != 200:
            print(f"[ERRO Status]: {resp.status_code}")
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')
        listings = []

        for row in soup.select('div.market_listing_row.market_recent_listing_row'):
            price_tag = row.select_one('span.market_listing_price')
            if not price_tag: continue
            price_text = price_tag.get_text(strip=True)
            price_match = re.search(r'R\$ ([\d.,]+)', price_text)
            if not price_match: continue
            price = float(price_match.group(1).replace('.', '').replace(',', '.'))

            link_tag = row.find('a', href=True)
            if not link_tag: continue
            link = link_tag['href']

            script = row.find_next_sibling('script')
            if not script or not script.string: continue
            inspect_match = re.search(r'"(steam://rungame[^"]+)"', script.string)
            if not inspect_match: continue
            inspect_link = inspect_match.group(1)

            float_val = get_float_csgofloat(inspect_link)
            if float_val is None: continue

            listings.append({'price': price, 'float': float_val, 'link': link})
            if len(listings) >= 3: break

        if listings:
            last_float_success = time.time()
        return listings

    except Exception as e:
        print(f"[ERRO Listagens]: {e}")
        return None

@tasks.loop(minutes=30)
async def check_price():
    print(f"\nVerificando... {time.strftime('%H:%M')}")
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("Canal não encontrado!")
        return

    price, volume = get_price()
    if price is None:
        print("Falha ao pegar preço.")
        return
    if price >= MAX_PRICE:
        print(f"Preço: R$ {price:,.2f} → acima do limite.")
        return

    print(f"ALERTA! R$ {price:,.2f}")
    listings = get_listings_with_float()

    embed = discord.Embed(
        title="OPORTUNIDADE! Nomad Knife Urban Masked (FT)",
        color=0x00ff00,
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="Preço Steam", value=f"R$ {price:,.2f}", inline=True)
    embed.add_field(name="Volume 24h", value=volume, inline=True)

    if listings:
        for item in listings:
            embed.add_field(
                name=f"R$ {item['price']:,.2f} | Float: {item['float']}",
                value=f"[Comprar]({item['link']})",
                inline=False
            )
        embed.set_footer(text="Float via csgofloat.com")
    else:
        embed.add_field(name="Float", value="Indisponível", inline=False)
        embed.set_footer(text="Tentando novamente em 10 min")

    await channel.send(embed=embed, content="<@274244315423834112>")

@client.event
async def on_ready():
    print(f'Bot online: {client.user}')
    if not check_price.is_running():
        check_price.start()

# ============= INICIAR AMBOS =============
if __name__ == '__main__':
    # Inicia Flask em thread separada
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Inicia Discord
    client.run(TOKEN)