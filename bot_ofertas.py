import asyncio
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

# ==========================================
# 0. CONFIGURAÇÕES GERAIS E AMBIENTE
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "-1003828035343")
INTERVALO_VARREDURA = int(os.environ.get("INTERVALO_SEGUNDOS", "900"))  # 15 min padrão

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ==========================================
# 1. SERVIDOR WEB LEVE (KEEP-ALIVE NO RENDER)
# ==========================================
class ServidorStatus(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Robo Tchicah rodando com sucesso 24h!")

    def log_message(self, format, *args):
        return  # Silencia logs HTTP no terminal

def iniciar_servidor_render():
    porta = int(os.environ.get("PORT", 8080))
    servidor = HTTPServer(("0.0.0.0", porta), ServidorStatus)
    print(f"[Render] Servidor web ativo na porta {porta}", flush=True)
    servidor.serve_forever()

threading.Thread(target=iniciar_servidor_render, daemon=True).start()

# ==========================================
# 2. BANCO DE DADOS LOCAL (SQLITE)
# ==========================================
def inicializar_banco():
    with sqlite3.connect("ofertas.db") as conexao:
        cursor = conexao.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS postadas (
                id TEXT PRIMARY KEY,
                titulo TEXT,
                data_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conexao.commit()

def oferta_ja_postada(id_oferta: str) -> bool:
    with sqlite3.connect("ofertas.db") as conexao:
        cursor = conexao.cursor()
        cursor.execute("SELECT 1 FROM postadas WHERE id = ?", (id_oferta,))
        return cursor.fetchone() is not None

def salvar_oferta(id_oferta: str, titulo: str):
    with sqlite3.connect("ofertas.db") as conexao:
        cursor = conexao.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO postadas (id, titulo) VALUES (?, ?)",
            (id_oferta, titulo),
        )
        conexao.commit()

# ==========================================
# 3. SCRAPERS DE OFERTAS
# ==========================================
def raspar_mercado_livre() -> list:
    ofertas = []
    url = "https://www.mercadolivre.com.br/ofertas"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"[ML Status] Código HTTP retornado: {res.status_code}", flush=True)
            return ofertas

        soup = BeautifulSoup(res.text, "html.parser")
        itens = soup.select(".promotion-item")
        print(f"[ML] Encontrados {len(itens)} itens brutos na página", flush=True)

        for item in itens[:10]:
            link_tag = item.select_one("a.promotion-item__link-container")
            titulo_tag = item.select_one(".promotion-item__title")
            preco_tag = item.select_one(".andes-money-amount__fraction")
            img_tag = item.select_one("img")

            if link_tag and titulo_tag and preco_tag:
                link = link_tag.get("href", "").split("#")[0]
                img_url = img_tag.get("src") or img_tag.get("data-src") if img_tag else ""
                id_oferta = link.split("/p/")[-1] if "/p/" in link else link[-30:]

                ofertas.append({
                    "id": id_oferta,
                    "loja": "Mercado Livre",
                    "titulo": titulo_tag.get_text(strip=True),
                    "preco": f"R$ {preco_tag.get_text(strip=True)}",
                    "link": link,
                    "imagem": img_url
                })
    except Exception as e:
        print(f"[Erro Mercado Livre] {e}", flush=True)
    return ofertas

def raspar_magalu(categoria="celulares-e-smartphones/l/te/") -> list:
    ofertas = []
    url = f"https://www.magazineluiza.com.br/{categoria}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"[Magalu Status] Código HTTP retornado: {res.status_code}", flush=True)
            return ofertas

        soup = BeautifulSoup(res.text, "html.parser")
        itens = soup.select("[data-testid='product-card-container']")
        print(f"[Magalu] Encontrados {len(itens)} itens brutos na página", flush=True)

        for item in itens[:10]:
            link_tag = item.select_one("a")
            titulo_tag = item.select_one("[data-testid='product-card-title']")
            preco_tag = item.select_one("[data-testid='price-value']")
            img_tag = item.select_one("img")

            if link_tag and titulo_tag and preco_tag:
                href = link_tag.get("href", "")
                link = f"https://www.magazineluiza.com.br{href}" if href.startswith("/") else href
                img_url = img_tag.get("src", "") if img_tag else ""

                ofertas.append({
                    "id": link.split("/p/")[1][:20] if "/p/" in link else link[-30:],
                    "loja": "Magazine Luiza",
                    "titulo": titulo_tag.get_text(strip=True),
                    "preco": preco_tag.get_text(strip=True),
                    "link": link,
                    "imagem": img_url
                })
    except Exception as e:
        print(f"[Erro Magalu] {e}", flush=True)
    return ofertas

# ==========================================
# 4. ENVIO PARA O TELEGRAM
# ==========================================
async def despachar_para_telegram(bot: Bot, item: dict):
    texto = (
        f"🔥 <b>{item['titulo']}</b>\n\n"
        f"💰 <b>Preço:</b> {item['preco']}\n"
        f"🏬 <b>Loja:</b> {item['loja']}\n"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Ver Oferta", url=item["link"])]
    ])

    try:
        if item.get("imagem") and item["imagem"].startswith("http"):
            await bot.send_photo(
                chat_id=CHAT_ID,
                photo=item["imagem"],
                caption=texto,
                parse_mode=ParseMode.HTML,
                reply_markup=teclado
            )
        else:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=texto,
                parse_mode=ParseMode.HTML,
                reply_markup=teclado,
                disable_web_page_preview=False
            )
        print(f"[Postado] {item['loja']} - {item['titulo'][:35]}...", flush=True)
        salvar_oferta(item["id"], item["titulo"])
        await asyncio.sleep(3)  # Pausa contra rate limit
    except Exception as e:
        print(f"[Falha no Envio] Destino ({CHAT_ID}): {e}", flush=True)

# ==========================================
# 5. CICLO PRINCIPAL (LOOP AUTOMÁTICO)
# ==========================================
async def main():
    if not BOT_TOKEN:
        print("[Erro Crítico] BOT_TOKEN não encontrado nas variáveis de ambiente.", flush=True)
        return

    inicializar_banco()
    bot = Bot(token=BOT_TOKEN)
    print(f"[Status] Bot iniciado com sucesso. Conectando com {CHAT_ID}...", flush=True)

    # TESTE DE CONEXÃO INICIAL DIRETO NO TELEGRAM
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="🤖 <b>Tchicah Bot online!</b>\nMonitoramento de ofertas ativado.",
            parse_mode=ParseMode.HTML
        )
        print("[Status] Mensagem de teste enviada com sucesso ao grupo!", flush=True)
    except Exception as e:
        print(f"[Erro de Teste Telegram] Não foi possível enviar ao chat {CHAT_ID}: {e}", flush=True)

    while True:
        print("\n--- Iniciando nova varredura de ofertas ---", flush=True)
        ofertas = []
        
        # Coleta de produtos
        ofertas.extend(raspar_mercado_livre())
        ofertas.extend(raspar_magalu())

        novas = 0
        for item in ofertas:
            if not oferta_ja_postada(item["id"]):
                await despachar_para_telegram(bot, item)
                novas += 1

        print(f"--- Varredura finalizada. Postadas agora: {novas}. Próxima em {INTERVALO_VARREDURA}s ---", flush=True)
        await asyncio.sleep(INTERVALO_VARREDURA)

if __name__ == "__main__":
    asyncio.run(main())
