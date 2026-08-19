import os
import time
import sqlite3
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import asyncio

# ==========================================
# 0. SERVIDOR WEB LEVE (PARA O RENDER NÃO DAR TIMEOUT)
# ==========================================
class ServidorStatus(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Robo Tchicah rodando com sucesso 24h!")

    def log_message(self, format, *args):
        return  # Silencia logs desnecessários no terminal

def iniciar_servidor_render():
    porta = int(os.environ.get("PORT", 8080))
    servidor = HTTPServer(("0.0.0.0", porta), ServidorStatus)
    print(f"Servidor web de monitoramento ativo na porta {porta}")
    servidor.serve_forever()

# Inicia o servidor em segundo plano
threading.Thread(target=iniciar_servidor_render, daemon=True).start()

# ==========================================
# CONFIGURAÇÕES GERAIS (PT-BR)
# ==========================================
TELEGRAM_TOKEN = "8513284486:AAF2cCs8BFf4tr4_FNA5EBf92N9-mm4HP0o"
CHAT_ID = "@tchicah"  # Canal ou grupo destino

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

def formatar_moeda_br(valor: float) -> str:
    valor_formatado = f"{valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    return f"R$ {valor_formatado}"

# ==========================================
# 1. BANCO DE DADOS (CONTROLE DE DUPLICATAS)
# ==========================================
def inicializar_banco():
    conn = sqlite3.connect("ofertas_lojas.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ofertas (
            id_produto TEXT PRIMARY KEY,
            loja TEXT,
            titulo TEXT,
            preco REAL,
            data_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def ja_enviado(id_produto: str) -> bool:
    conn = sqlite3.connect("ofertas_lojas.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM ofertas WHERE id_produto = ?", (id_produto,))
    existe = cursor.fetchone() is not None
    conn.close()
    return existe

def salvar_oferta(id_produto: str, loja: str, titulo: str, preco: float):
    conn = sqlite3.connect("ofertas_lojas.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ofertas (id_produto, loja, titulo, preco) VALUES (?, ?, ?, ?)",
        (id_produto, loja, titulo, preco)
    )
    conn.commit()
    conn.close()

# ==========================================
# 2. RASPAGEM DAS LOJAS
# ==========================================
def raspar_mercado_livre(termo_busca="ofertas-do-dia"):
    url = f"https://lista.mercadolivre.com.br/{termo_busca}_OrderId_PRICE_DISCOUNT"
    ofertas = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.find_all("li", class_="ui-search-layout__item")

        for card in cards[:10]:
            try:
                link_tag = card.find("a", class_="poly-component__title") or card.find("a")
                link = link_tag["href"].split("?")[0]
                id_prod = f"ML_{link.split('/')[-1]}"
                titulo = link_tag.text.strip()
                
                preco_container = card.find("span", class_="andes-money-amount--cents-superscript")
                if not preco_container:
                    continue
                fracao = preco_container.find("span", class_="andes-money-amount__fraction").text.replace(".", "")
                preco = float(fracao)

                desconto_tag = card.find("span", class_="andes-money-amount__discount")
                desconto = desconto_tag.text.strip() if desconto_tag else "Super Desconto"

                img_tag = card.find("img")
                imagem = img_tag.get("data-src") or img_tag.get("src") if img_tag else None

                if not ja_enviado(id_prod):
                    ofertas.append({
                        "id": id_prod,
                        "loja": "Mercado Livre",
                        "titulo": titulo,
                        "preco": preco,
                        "desconto": desconto,
                        "link": link,
                        "imagem": imagem
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[Erro Mercado Livre]: {e}")
    return ofertas

def raspar_amazon(termo_busca="eletronicos"):
    url = f"https://www.amazon.com.br/s?k={termo_busca}"
    ofertas = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.find_all("div", {"data-component-type": "s-search-result"})

        for card in cards[:10]:
            try:
                asin = card.get("data-asin")
                if not asin:
                    continue
                id_prod = f"AMZ_{asin}"
                
                titulo = card.find("h2").text.strip()
                link = f"https://www.amazon.com.br/dp/{asin}"
                
                preco_int = card.find("span", class_="a-price-whole")
                preco_dec = card.find("span", class_="a-price-fraction")
                if not preco_int:
                    continue
                
                preco_str = preco_int.text.replace(".", "").replace(",", "")
                dec_str = preco_dec.text if preco_dec else "00"
                preco = float(f"{preco_str}.{dec_str}")
                
                img_tag = card.find("img", class_="s-image")
                imagem = img_tag["src"] if img_tag else None

                if not ja_enviado(id_prod):
                    ofertas.append({
                        "id": id_prod,
                        "loja": "Amazon Brasil",
                        "titulo": titulo,
                        "preco": preco,
                        "desconto": "Destaque",
                        "link": link,
                        "imagem": imagem
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[Erro Amazon]: {e}")
    return ofertas

def raspar_magalu(categoria="celulares-e-smartphones/l/te/"):
    url = f"https://www.magazineluiza.com.br/{categoria}"
    ofertas = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.find_all("li", {"data-testid": "product-card-container"})

        for card in cards[:10]:
            try:
                link_tag = card.find("a")
                link = "https://www.magazineluiza.com.br" + link_tag["href"].split("?")[0]
                id_prod = f"MGL_{link.split('/p/')[-1].split('/')[0]}"
                
                titulo = card.find("h2", {"data-testid": "product-title"}).text.strip()
                preco_tag = card.find("p", {"data-testid": "price-value"})
                
                if not preco_tag:
                    continue
                
                preco_limpo = preco_tag.text.replace("R$", "").replace(".", "").replace(",", ".").strip()
                preco = float(preco_limpo)
                
                img_tag = card.find("img")
                imagem = img_tag["src"] if img_tag else None

                if not ja_enviado(id_prod):
                    ofertas.append({
                        "id": id_prod,
                        "loja": "Magazine Luiza",
                        "titulo": titulo,
                        "preco": preco,
                        "desconto": "Preço Promocional",
                        "link": link,
                        "imagem": imagem
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[Erro Magazine Luiza]: {e}")
    return ofertas

# ==========================================
# 3. ENVIO FORMATADO PARA O TELEGRAM
# ==========================================
async def despachar_para_telegram(bot: Bot, item: dict):
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🛒 Ver Promoção na {item['loja']}", url=item['link'])]
    ])
    
    preco_formatado = formatar_moeda_br(item["preco"])
    
    mensagem = (
        f"🔥 **SUPER OFERTA: {item['loja'].upper()}**\n\n"
        f"📦 **{item['titulo']}**\n\n"
        f"🏷️ **Destaque:** {item['desconto']}\n"
        f"💰 **Preço:** {preco_formatado}\n"
    )
    
    try:
        if item.get("imagem"):
            await bot.send_photo(
                chat_id=CHAT_ID,
                photo=item["imagem"],
                caption=mensagem,
                reply_markup=teclado,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=mensagem,
                reply_markup=teclado,
                parse_mode="Markdown"
            )
        salvar_oferta(item["id"], item["loja"], item["titulo"], item["preco"])
        print(f"[Enviado com Sucesso] -> {item['titulo'][:35]}...")
        await asyncio.sleep(2)
    except Exception as e:
        print(f"[Falha no Envio] Destino ({CHAT_ID}): {e}")

# ==========================================
# 4. CICLO PRINCIPAL (LOOP AUTOMÁTICO)
# ==========================================
async def main():
    inicializar_banco()
    bot = Bot(token=TELEGRAM_TOKEN)
    print("==================================================")
    print(" 🚀 Robô Rastreador de Ofertas Iniciado com Sucesso!")
    print(f" 📢 Canal de Destino: {CHAT_ID}")
    print("==================================================")

    while True:
        novas_ofertas = []
        
        print("\n🔍 Iniciando nova varredura de produtos...")
        novas_ofertas.extend(raspar_mercado_livre("eletronicos"))
        novas_ofertas.extend(raspar_amazon("ofertas"))
        novas_ofertas.extend(raspar_magalu())
        
        print(f"📦 Total de novas oportunidades encontradas: {len(novas_ofertas)}")
        
        for oferta in novas_ofertas:
            await despachar_para_telegram(bot, oferta)
            
        print("\n⏳ Varredura concluída. Aguardando 15 minutos para a próxima rodada...")
        await asyncio.sleep(900)

if __name__ == "__main__":
    asyncio.run(main())
                
