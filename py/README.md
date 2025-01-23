# Ethereum Cüzdan Bulucu

Bu program, rastgele Ethereum cüzdanları oluşturur ve bakiyelerini kontrol eder. Bakiyesi olan cüzdanlar bulunduğunda bunları kaydeder.

## Özellikler

- Rastgele Ethereum cüzdanları oluşturma
- Cüzdan bakiyelerini kontrol etme
- Bakiyeli cüzdanları kaydetme
- İlerleme göstergesi
- Performans istatistikleri
- CSV formatında loglama
- Test modu
- Çoklu iş parçacığı desteği

## Gereksinimler

```bash
pip install web3 eth-account mnemonic
```

## Kullanım

### Temel Kullanım

```bash
python eth_finder.py
```

### Parametreler

- `--test`: Test modunda çalıştır (gerçek bakiye kontrolü yapmaz)
- `--output`: Çıktı dosyası (varsayılan: wallets.json)
- `--threads`: İş parçacığı sayısı (varsayılan: 4)
- `--limit`: Üretilecek cüzdan sayısı
- `--save`: Taranan cüzdanları kaydet
- `--delay`: Her cüzdan üretimi arasındaki bekleme süresi (saniye)

### Örnekler

Test modunda çalıştırma:
```bash
python eth_finder.py --test
```

100 cüzdan üret:
```bash
python eth_finder.py --limit 100
```

Sonuçları kaydet:
```bash
python eth_finder.py --save
```

8 iş parçacığı ile çalıştır:
```bash
python eth_finder.py --threads 8
```

İstekler arası 1 saniye bekle:
```bash
python eth_finder.py --delay 1
```

## Çıktılar

1. **Konsol Çıktısı**: Program çalışırken her üretilen cüzdanın detaylarını ve ilerleme durumunu gösterir.

2. **Log Dosyası**: Her tarama için yeni bir log dosyası oluşturulur (wallet_scan_YYYYMMDD_HHMMSS.log).
   - CSV formatında
   - Timestamp, Adres, Seed Phrase ve Bakiye bilgilerini içerir

3. **JSON Dosyası**: `--save` parametresi kullanıldığında bulunan cüzdanlar JSON formatında kaydedilir.

## Notlar

- Program Ctrl+C ile güvenli bir şekilde durdurulabilir
- Test modu gerçek bakiye kontrolü yapmaz, rastgele test verileri üretir
- Infura API kullanıldığı için istek limitlerine dikkat edilmelidir
- Çok fazla istek göndermemek için her bakiye kontrolü arasında 0.5 saniye bekleme süresi vardır 