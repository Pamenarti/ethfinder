import asyncio
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
import time
from concurrent.futures import ThreadPoolExecutor

async def fetch_page(session, page, headers):
    url = f'https://etherscan.io/accounts/{page}?ps=100'
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.text()
            print(f"Sayfa {page} yüklenemedi. Durum kodu: {response.status}")
            return None
    except Exception as e:
        print(f"Hata oluştu, sayfa {page}: {str(e)}")
        return None

def parse_html(html):
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    address_links = soup.select('td a.js-clipboard')
    return [link.get('data-clipboard-text') for link in address_links if link.get('data-clipboard-text')]

async def scrape_addresses():
    addresses = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    async with aiohttp.ClientSession() as session:
        tasks = []
        # 5'er sayfalık gruplar halinde işlem yapalım
        for page in range(1, 101):
            tasks.append(fetch_page(session, page, headers))
            if len(tasks) >= 5 or page == 100:
                htmls = await asyncio.gather(*tasks)
                
                with ThreadPoolExecutor() as executor:
                    for html in executor.map(parse_html, htmls):
                        addresses.extend(html)
                
                print(f"Sayfalar {page-len(tasks)+1}-{page} tamamlandı.")
                tasks = []
                # Daha kısa bir bekleme süresi
                await asyncio.sleep(0.5)

    # Adresleri dosyaya kaydet
    async with aiofiles.open('ethrichlist.txt', 'w') as f:
        await f.write('\n'.join(addresses) + '\n')

    print(f"Toplam {len(addresses)} adres kaydedildi.")

if __name__ == "__main__":
    print("Adresler çekiliyor...")
    start_time = time.time()
    
    asyncio.run(scrape_addresses())
    
    end_time = time.time()
    print(f"İşlem tamamlandı. Süre: {end_time - start_time:.2f} saniye")
    print("Sonuçlar ethrichlist.txt dosyasına kaydedildi.")
