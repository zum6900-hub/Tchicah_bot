import asyncio
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

async def main():
    inicializar_banco()
    bot = Bot(token=os.environ.get("BOT_TOKEN"))
    
    while True:
        try:
            print("[Info] Iniciando nova varredura de ofertas...")
            # Chamada das funções de scraping
            # ofertas = raspar_magalu() + raspar_amazon() ...
            # for item in ofertas:
            #     await despachar_para_telegram(bot, item)
            
            print("[Info] Varredura concluída. Aguardando próximo ciclo...")
        except Exception as e:
            print(f"[Erro no Ciclo]: {e}")
        
        # Pausa entre varreduras (ex: 15 minutos = 900 segundos)
        await asyncio.sleep(900)

if __name__ == "__main__":
    asyncio.run(main())
    
                
