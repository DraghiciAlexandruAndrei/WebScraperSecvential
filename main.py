import requests
import time
import math
import json
import csv

# ============================================================
#  CONFIGURARE — avem constante pt a le putea inlocui mai usor
# ============================================================
QUERY_TERM   = "parallel distributed computing"   # termenul de cautare
TARGET_COUNT = 1000 # cate articole vrei (max 1000)
# ============================================================

DBLP_API_URL = "https://dblp.org/search/publ/api"
PAGE_SIZE    = 30    # API-ul DBLP e stabil cu 30

#trimite o cerere la Api
# reincearca daca gaseste vreo eroare
def safe_request(url, params, retries=3):
    """
    GET cu retry automat. Returneaza Response sau None.
    Afișează motivul erorii pentru debugging.
    """
    #antet user-agent  care indentifica scriptul
    headers = {"User-Agent": "Mozilla/5.0 (compatible; StudentProject/1.0)"}
    #bucla de retry
    for attempt in range(retries):
        try:
            #trimte cerea propriu zisa
            response = requests.get(url, params=params, headers=headers, timeout=15)
            #daca da coul 200 => OK
            if response.status_code == 200:
                return response

            #am trimis prea multe cereri prea repede
            if response.status_code == 429: #429 limita de rate
                wait = int(response.headers.get("Retry-After", 10))
                print(f"Rate limit. Așteptăm {wait} secunde...")
                time.sleep(wait)
                continue
            # Eroare de server la DBLP
            if response.status_code == 500:
                print(f"   HTTP 500 — eroare server la încercarea {attempt + 1}/3")
                print(f"   URL: {response.url}")
                # Pauza inainte de retry la eroare 500
                time.sleep(2)
                continue
            #orice alt status HTTP
            print(f"    HTTP {response.status_code} — {response.url}")

        #tratam exceptiile
        #timeout
        except requests.exceptions.Timeout:
            print(f"    Timeout la incercarea {attempt + 1}.")
        #conexiune
        except requests.exceptions.ConnectionError:
            print("     Eroare de conexiune.")
        #eroare neprevazuta
        except Exception as e:
            print(f"    Eroare neprevazuta: {e}")

        time.sleep(2)
    #daca toate retry nu merg
    print("    Toate retry-urile au esuat pentru aceasta pagina.")
    #returnam none ca sa nu se blocheze
    return None

#trb sa primeasca un obiect de tip json din dblp
#dupa care extrage campurile utile
#il transforma intr-un dictionar (array) python
def parse_hit(hit):
    """
    Extrage campurile dintr-un rezultat JSON DBLP.
    Returnează un dicționar sau None dacă lipsesc datele esențiale.
    """
    #acesam campul info din html
    info = hit.get("info", {})

    title = info.get("title")
    if not title:
        return None

    # Autori — pot fi dict (un singur autor) sau lista
    authors_raw = info.get("authors", {}).get("author", [])
    if isinstance(authors_raw, dict):
        authors_raw = [authors_raw]
    authors = [a.get("text", "") for a in authors_raw]

    year = info.get("year", "N/A")
    link = info.get("url", None)
    doi  = info.get("doi", None) #digital object identifier
    """
    Un dictionar py  = array (set de date neordonate) 
    si indexate prin chei unice
    """
    #standardizam dictionarul
    #returneaza dictionarul
    return {
        "title":   title,
        "authors": authors,
        "year":    year,
        "link":    link,
        "doi":     doi, #digital object identifier
    }

#functia de scrape
def scrape_dblp(query, total_records):
    """
    Colectează `total_records` articole de la API-ul JSON DBLP.
    Returnează: (lista_articole, durata_în_secunde)
    """
    #lista pentru rezultate
    all_results  = []
    seen_titles  = set() # set de deduplicare
    needed_pages = math.ceil(total_records / PAGE_SIZE) #cate pagini cere API

    print(f"\n{'='*55}")
    print(f"  Cautare: \"{query}\"")
    print(f"  Target:  {total_records} articole (~{needed_pages} pagini)")
    print(f"  API:     {DBLP_API_URL}")
    print(f"{'='*55}")
    #incepem timerul
    start_time = time.perf_counter()
    #bucla de paginare
    for page in range(needed_pages):
        #se opreste daca avem destule articole
        if len(all_results) >= total_records:
            break

        #calculeaza ofsetul si cate articole ne mai trebuie
        offset      = page * PAGE_SIZE
        hits_needed = min(PAGE_SIZE, total_records - len(all_results))
        #parametri interogare Dblp
        params = {
            "q":      query,
            "format": "json",
            "h":      hits_needed, #articole / pagina
            "f":      offset, # de unde incepe DBLP sa trimita articole
            "c":      0,
        }

        print(f"[Pagina {page + 1}/{needed_pages}] offset={offset}, h={hits_needed}...")

        #trimitem cererea prin funtia de request
        response = safe_request(DBLP_API_URL, params)
        #daca nu primeste raspuns sare pagina
        if response is None:
            print(f"Pagina {page + 1} sărita complet.")
            time.sleep(2)
            continue

        # Verificare ca raspunsul e JSON valid
        try:
            data = response.json()
        except ValueError:
            print(f"  Raspuns invalid (nu e JSON). Primii 200 chars:")
            print(f"  {response.text[:200]}")
            continue

        #extragem lista de hit din JSON
        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        #daca nu mai sunt articole atunci se opreste
        if not hits:
            total_available = data.get("result", {}).get("hits", {}).get("@total", "?")
            print(f"  ℹ️  Nu mai sunt rezultate. Total disponibil pe DBLP: {total_available}")
            break

        added = 0
        #parcurgem rezultatele paginarii
        for hit in hits:
            article = parse_hit(hit)
            if not article:
                continue
            #evitare duplicate
            if article["title"] in seen_titles:
                continue
            seen_titles.add(article["title"])
            all_results.append(article)
            added += 1

        print(f"  +{added} articole noi | Total: {len(all_results)} / {total_records}")

        if page < needed_pages - 1:
            time.sleep(0.5)
    #Creem lista finala de date
    final_data = all_results[:total_records]
    #calculam timpul de extragere
    duration   = time.perf_counter() - start_time

    #daca dblp are mai putine articole decat s-au cerut atunci opreste
    if len(final_data) < total_records:
        print(f"\n  Colectate doar {len(final_data)} din {total_records} cerute.")
        print("   DBLP nu are suficiente rezultate pentru acest query.")

    return final_data, duration

# functie pentru afisarea rezulatelor in consola
def print_results(data, duration):
    """Afisează un sumar al rezultatelor in consola."""
    print(f"\n{'='*55}") #55 de caractere / linie
    print(f"  Rezultat final: {len(data)} articole în {duration:.2f} secunde")
    print(f"{'='*55}")
    #scoatem 5 autor+ publicatie
    for i, art in enumerate(data[:5], 1): # data taie lista si pastreaza decat 5 articole
        #construim numele autorilor
        authors_str = ", ".join(art['authors'][:2])
        if len(art['authors']) > 2:
            authors_str += " et al."
        #afisam titlul, autorii si linkul
        print(f"\n  {i}. [{art['year']}] {art['title'][:70]}")
        print(f"     Autori: {authors_str}")
        print(f"     Link:   {art['link']}")
    #daca sunt mai mult de 5 articole afisam
    if len(data) > 5:
        print(f"\n  ... și încă {len(data) - 5} articole.")

#functie de salvare a datelor in json
def save_to_json(data, filename="rezultate_dblp.json"):
    """
    Salveaza lista de dicționare într-un fișier format JSON.
    """
    try:
        with open(filename, "w", encoding="utf-8") as f:
            # indent=4 face fișierul ușor de citit (human-readable)
            # ensure_ascii=False permite salvarea corecta a diacriticelor sau caracterelor speciale
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"\nSucces! {len(data)} articole au fost salvate în: {filename}")
    except Exception as e:
        print(f"Eroare la salvarea fișierului: {e}")

#salveaza datele in excell
def save_to_csv(data, filename="rezultate_dblp.csv"):
    """
    Salveaza lista de dictionare intr-un fisier CSV
    Transforma listele de autori in siruri de text separate prin punct si virgula.
    """
    if not data:
        print("Nu există date de salvat în CSV.")
        return

    try:
        # Extragem capul de tabel (keys) din primul dictionar
        keys = data[0].keys()

        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            # utf-8-sig ajută Excel să recunoasca caracterele speciale corect
            writer = csv.DictWriter(f, fieldnames=keys)

            # Scriem prima linie (header-ul)
            writer.writeheader()

            # Pregatim datele pentru CSV (listele de autori devin string-uri)
            for row in data:
                # Facem o copie a rândului pentru a nu modifica datele originale din RAM
                clean_row = row.copy()
                if isinstance(clean_row["authors"], list):
                    clean_row["authors"] = "; ".join(clean_row["authors"])

                writer.writerow(clean_row)

        print(f"Succes! {len(data)} articole au fost salvate în format CSV: {filename}")
    except Exception as e:
        print(f"Eroare la salvarea CSV: {e}")
# ============================================================
#  PUNCT DE INTRARE
# ============================================================
if __name__ == "__main__":
    #colectam datele
    data, t = scrape_dblp(QUERY_TERM, TARGET_COUNT)
    #afisam rezultatele in consola
    print_results(data, t)

    if data:
        save_to_json(data, "articole.json")
        save_to_csv(data, "articole_secvential.csv")