def run_startup_worker(memoria):
    try:
        queue = []
        visti = set()

        # 1. Raccogliamo i link (Livello 1)
        for nome_fonte, url in URLS_STARTUP.items():
            try:
                response = requests.get(url, timeout=15)
                soup = BeautifulSoup(response.text, "html.parser")
                for link_tag in soup.find_all('a', href=True):
                    href = link_tag['href'].lower()
                    testo_l = link_tag.text.strip().lower()
                    if not any(k in testo_l for k in KEYWORDS_STARTUP) and not any(k in href for k in KEYWORDS_STARTUP): continue
                    if any(x in href for x in ["facebook", "twitter", "instagram", "linkedin", "youtube"]): continue
                    
                    real_url = link_tag['href'] if link_tag['href'].startswith("http") else urljoin(url, link_tag['href'])
                    if real_url == url: continue
                    
                    if real_url not in visti:
                        visti.add(real_url)
                        queue.append({"titolo": link_tag.text.strip(), "url": real_url, "depth": 1})
            except: pass

        # 2. Scaviamo!
        while queue:
            item = queue.pop(0)
            titolo_link, real_url, depth = item["titolo"], item["url"], item["depth"]

            id_bando = "start_" + generate_hash(real_url)
            if memoria.get(id_bando, {}).get("stato") in ["ignorato", "partecipo"]: continue
            
            if id_bando not in memoria:
                logging.info(f"🚀 Analizzo (Livello {depth}): {titolo_link[:30] or real_url[:30]}")
                testo_completo = estrai_testo_startup(real_url)
                time.sleep(5)
                
                dati_ai = analizza_startup_con_ai(testo_completo)
                scadenza = str(dati_ai.get("scadenza", "N.D."))
                if scadenza == "Errore": continue
                
                try: score = int(''.join(filter(str.isdigit, str(dati_ai.get("voto", "5")))))
                except: score = 5

                # 🛑 SE SCARTATO -> ESPLORA I LINK INTERNI
                if score < 5:
                    memoria[id_bando] = {"stato": "ignorato", "data_rilevazione": datetime.now().strftime("%d/%m/%Y")}
                    if depth < 2:
                        logging.info(f"🔄 Esploro sotto-link da: {real_url}")
                        try:
                            sub_resp = requests.get(real_url, timeout=15)
                            sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                            for sub_a in sub_soup.find_all('a', href=True):
                                s_href = sub_a['href'].lower()
                                s_testo = sub_a.text.strip().lower()
                                if not any(k in s_testo for k in KEYWORDS_STARTUP) and not any(k in s_href for k in KEYWORDS_STARTUP): continue
                                if any(x in s_href for x in ["facebook", "twitter", "instagram", "linkedin", "youtube"]): continue
                                
                                next_url = sub_a['href'] if sub_a['href'].startswith("http") else urljoin(real_url, sub_a['href'])
                                if next_url not in visti:
                                    visti.add(next_url)
                                    queue.append({"titolo": sub_a.text.strip(), "url": next_url, "depth": depth + 1})
                        except: pass
                    continue

                # ✅ BANDO TROVATO
                ente = dati_ai.get('ente', 'N.D.')
                tipo_fondo = dati_ai.get('tipo_fondo', 'N.D.')
                requisiti = dati_ai.get('requisiti', 'N.D.')

                msg = f"🚀 **BANDO STARTUP ({score}/10)**\n\n📌 *{titolo_link or 'Vedi link'}*\n🏢 **Ente:** {ente}\n⏳ **Scadenza:** `{scadenza}`\n💰 **Tipo:** {tipo_fondo}\n📝 **Requisiti:** _{requisiti}_"
                invia_telegram(msg, [
                    [{"text": "🌐 Vai al Bando", "url": real_url}],
                    [{"text": "✅ Partecipo", "callback_data": f"partecipo:{id_bando}"},
                     {"text": "❌ Ignora", "callback_data": f"ignora_bando:{id_bando}"}],
                    [{"text": "📊 Dashboard", "url": "https://andrydex.github.io/andrydex_slave/"}]
                ])
                
                memoria[id_bando] = {
                    "stato": "nuovo", "titolo": titolo_link or "Bando Startup", "url": real_url, "tipo": "startup",
                    "scadenza": scadenza, "ente": ente, "requisiti": requisiti, "fondo": tipo_fondo,
                    "voto": score, "data_rilevazione": datetime.now().strftime("%d/%m/%Y")
                }
        update_health("startup_worker", "ok")
    except Exception as e:
        logging.error(f"Errore startup_worker: {e}")
        update_health("startup_worker", f"error: {str(e)}")
    
    return memoria
