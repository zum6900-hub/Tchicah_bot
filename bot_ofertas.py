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
    """Envia a foto, legenda em Português e o botão com link da loja."""
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🛒 Ver Promoção na {item['loja']}", url=item['link'])]
    ])
    
    preco_formatado = formatar_moeda_br(item["preco"])
    
    mensagem = (
        f"🔥 SUPER OFERTA: {item['loja'].upper()}\n\n"
        f"📦 {item['titulo']}\n\n"
        f"🏷️ Destaque: {item['desconto']}\n"
        f"💰 Preço: {preco_formatado}\n"
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
        await asyncio.sleep(2)  # Pausa de segurança contra limite de envio do Telegram
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

if name == "main":
    asyncio.run(main())
