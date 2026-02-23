#!/usr/bin/env python3
import csv
import json
import time
import sys
import os
from datetime import datetime
from urllib.parse import urlencode
import urllib.request
import urllib.error
import ssl

# Lisää parent-kansio pathiin
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.asetukset import *
except ImportError:
    print("Virhe: config/asetukset.py puuttuu!")
    print("Kopioi config/asetukset.py.example -> config/asetukset.py")
    print("Ja lisää oma SerpAPI-avain")
    sys.exit(1)

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def lue_ja_suodata_csv(filepath, max_rows=None):
    """Lukee ja suodattaa CSV:n"""
    yritykset = []
    
    kampaamo_avainsanat = [
        'kampaamo', 'parturi', 'hius', 'kampaus', 'hiusten',
        'parturi-kampaamo', 'hiusstudio', 'hair', 'barber',
        'hiuspaja', 'kampauspalvelu'
    ]
    
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=';')
            
            for row in reader:
                toimiala = row.get('toimiala', '').lower()
                toimialakoodi = row.get('toimialakoodi', '')
                nimi = row.get('nimi', '').lower()
                
                tasmaa = False
                
                # Toimialakoodi 96210 = kampaamo/parturi
                if toimialakoodi == "96210":
                    tasmaa = True
                
                # Toimialan nimi
                if any(avain in toimiala for avain in kampaamo_avainsanat):
                    tasmaa = True
                
                # Yrityksen nimi
                if any(avain in nimi for avain in kampaamo_avainsanat):
                    tasmaa = True
                
                if tasmaa:
                    yritykset.append(row)
                    if max_rows and len(yritykset) >= max_rows:
                        break
        
        print(f"Löytyi {len(yritykset)} kampaamoa/parturia")
        return yritykset
        
    except FileNotFoundError:
        print(f"Virhe: Tiedostoa {filepath} ei löytynyt!")
        print("Varmista että ytj_tulos.csv on data/-kansiossa")
        return []
    except Exception as e:
        print(f"Virhe: {e}")
        return []


def hae_serpapi(nimi, kaupunki=None):
    """Hakee yrityksen SerpAPI:sta"""
    
    query = f"{nimi}"
    if kaupunki:
        query += f" {kaupunki}"
    query += " Suomi"
    
    params = {
        'engine': 'google_maps',
        'q': query,
        'api_key': SERPAPI_KEY,
        'hl': 'fi',
        'gl': 'fi',
        'type': 'search'
    }
    
    url = f"https://serpapi.com/search?{urlencode(params)}"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if 'error' in data:
                return {'virhe': data['error']}
            
            results = data.get('local_results', [])
            if not results:
                results = [data['place_results']] if 'place_results' in data else []
            
            if not results:
                return None
            
            best = results[0]
            
            return {
                'nimi': best.get('title', ''),
                'osoite': best.get('address', ''),
                'puhelin': best.get('phone', ''),
                'verkkosivu': best.get('website', ''),
                'tyyppi': best.get('type', ''),
                'rating': best.get('rating', ''),
                'reviews': best.get('reviews', ''),
                'aukiolo': best.get('hours', ''),
                'sijainti': best.get('gps_coordinates', {})
            }
            
    except Exception as e:
        return {'virhe': str(e)}


def main():
    print("=" * 60)
    print("YTJ - Kampaamojen yhteystietojen haku")
    print("=" * 60)
    
    # Tarkista että data-kansiossa on tiedosto
    if not os.path.exists(INPUT_FILE):
        print(f"\nVirhe: {INPUT_FILE} ei löytynyt!")
        print("\nOhjeet:")
        print("1. Luo kansio 'data/' jos puuttuu")
        print("2. Kopioi ytj_tulos.csv tiedostoon data/ytj_tulos.csv")
        print("3. Älä lisää CSV:tä GitHubiin (.gitignore suojaa)")
        return
    
    # Lue ja suodata
    yritykset = lue_ja_suodata_csv(INPUT_FILE, max_rows=MAX_HAUT)
    
    if not yritykset:
        print("Ei kampaamoja löytynyt!")
        return
    
    # Prosessoi
    tulokset = []
    
    print(f"\nHaetaan {len(yritykset)} yrityksen tiedot...")
    print("-" * 60)
    
    for i, y in enumerate(yritykset, 1):
        nimi = y.get('nimi', '')
        kaupunki = y.get('kaupunki', '')
        
        print(f"[{i}/{len(yritykset)}] {nimi[:50]}")
        
        data = hae_serpapi(nimi, kaupunki)
        
        tulos = {
            'ytunnus': y.get('ytunnus', ''),
            'nimi': nimi,
            'kaupunki': kaupunki,
            'toimiala': y.get('toimiala', ''),
        }
        
        if data and 'virhe' not in data:
            print(f"  ✓ {data.get('nimi', '')}")
            if data.get('puhelin'):
                print(f"    📞 {data['puhelin']}")
            
            tulos.update({
                'löydetty_nimi': data.get('nimi', ''),
                'osoite': data.get('osoite', ''),
                'puhelin': data.get('puhelin', ''),
                'verkkosivu': data.get('verkkosivu', ''),
                'rating': data.get('rating', ''),
                'reviews': data.get('reviews', ''),
                'tyyppi': data.get('tyyppi', ''),
                'onnistui': True
            })
        else:
            print(f"  ✗ Ei löytynyt")
            tulos['onnistui'] = False
        
        tulokset.append(tulos)
        time.sleep(2)  # Rate limit
    
    # Tallenna
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(OUTPUT_DIR, f"kampaamot_{timestamp}.csv")
    
    # Varmista että output-kansio on olemassa
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=tulokset[0].keys(), delimiter=';')
        writer.writeheader()
        writer.writerows(tulokset)
    
    # Tilastot
    onnistuneet = sum(1 for t in tulokset if t.get('onnistui'))
    puhelimet = sum(1 for t in tulokset if t.get('puhelin'))
    
    print(f"\n{'='*60}")
    print(f"TALLENNETTU: {output_file}")
    print(f"{'='*60}")
    print(f"Tilastot:")
    print(f"  Yrityksiä: {len(tulokset)}")
    print(f"  Onnistui: {onnistuneet} ({onnistuneet/len(tulokset)*100:.1f}%)")
    print(f"  Puhelin: {puhelimet} ({puhelimet/len(tulokset)*100:.1f}%)")
    
    # Näytä puhelimet
    print(f"\nPuhelinnumerot:")
    for t in tulokset:
        if t.get('puhelin'):
            print(f"  {t['nimi'][:40]:40} | {t['puhelin']}")


if __name__ == "__main__":
    main()
