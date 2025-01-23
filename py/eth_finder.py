# -*- coding: utf-8 -*-
import os
import time
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from eth_account import Account
from web3 import Web3
import argparse
from mnemonic import Mnemonic
import secrets
from queue import Queue
from threading import Lock
import logging
from typing import List, Dict
import signal
import sys
import threading
# keyboard modülünü kaldır ve platform'a göre tuş yakalama ekle
if os.name == 'nt':  # Windows
    import msvcrt
else:  # Unix/Linux/MacOS
    import tty
    import termios

# Ethereum hesap oluşturma için güvenlik ayarı
Account.enable_unaudited_hdwallet_features()

# Infura node'una bağlanma (ücretsiz API kullanımı)
w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/14c9f44d16cf45af87a73cbdc4312ae8'))

class EthereumWalletGenerator:
    def __init__(self, output_file="wallets.json", test_mode=False, wallet_limit=None, save_wallets=False, delay=0):
        self.output_file = output_file
        self.test_mode = test_mode
        self.found_wallets = []
        self.total_generated = 0
        self.wallet_limit = wallet_limit  # Yeni: cüzdan limiti
        self.start_time = None
        self.last_stat_time = None
        self.display_format = "{:<4} | {:<42} | {:<20} | {:<90}"  # Sayaç, Adres, Bakiye ve seed için format
        self.mnemo = Mnemonic("english")
        self.save_wallets = save_wallets  # Yeni: kaydetme özelliği
        self.delay = delay  # Yeni: üretim gecikmesi (saniye)
        
        # Log dosyası için timestamp oluştur
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = f"wallet_scan_{timestamp}.log"
        print(f"Log dosyası: {self.log_file}")
        
        # Log başlık satırını yaz
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("Timestamp,Address,Seed Phrase,Balance\n")
        
        print("\n" + self.display_format.format("SIRA", "ADRES", "BAKİYE", "SEED PHRASE"))
        print("-" * 160)  # Ayırıcı çizgi
        
        self.wallet_queue = Queue(maxsize=1000)
        self.log_lock = Lock()
        self.save_lock = Lock()
        self.batch_size = 100  # Toplu işlem boyutu
        self.wallet_buffer = []  # Log için buffer
        self.running = True  # Durdurma bayrağı
        signal.signal(signal.SIGINT, self.signal_handler)  # Ctrl+C yakalayıcı
        self.stop_thread = None  # Yeni: tuş kontrolü için thread
        
    def signal_handler(self, signum, frame):
        """Ctrl+C sinyalini yakalar"""
        print("\n\n⚠️ Durdurma sinyali alındı. Program güvenli bir şekilde sonlandırılıyor...")
        self.running = False
        
    def generate_wallet(self):
        """Yeni bir Ethereum cüzdanı oluşturur"""
        # 12 kelimelik mnemonic oluştur
        mnemonic = self.mnemo.generate(strength=128)
        
        # Mnemonic'ten hesap oluştur
        account = Account.from_mnemonic(mnemonic)
        
        self.total_generated += 1
        
        wallet = {
            'address': account.address,
            'private_key': account.key.hex(),
            'seed_phrase': mnemonic,
            'balance': 0
        }
        
        return wallet
    
    def check_balance(self, address):
        """Cüzdan bakiyesini kontrol eder"""
        try:
            balance = w3.eth.get_balance(address)
            return w3.from_wei(balance, 'ether')
        except Exception as e:
            print(f"Hata: {e}")
            return 0
    
    def save_wallet_batch(self, wallets: List[Dict]):
        """Cüzdanları toplu olarak kaydeder"""
        if not self.save_wallets:  # Kaydetme özelliği kapalıysa hiçbir şey yapma
            return

        with self.save_lock:
            try:
                if os.path.exists(self.output_file):
                    with open(self.output_file, 'r') as f:
                        existing_wallets = json.load(f)
                else:
                    existing_wallets = []
                
                existing_wallets.extend(wallets)
                
                with open(self.output_file, 'w') as f:
                    json.dump(existing_wallets, f, indent=4)
            except Exception as e:
                print(f"Toplu kayıt hatası: {e}")

    def log_wallet_batch(self, entries: List[str]):
        """Cüzdan loglarını toplu olarak yazar"""
        with self.log_lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.writelines(entries)

    def process_wallet_batch(self, size=100):
        """Cüzdanları toplu olarak işler"""
        wallets = []
        log_entries = []
        
        for _ in range(size):
            if not self.running:  # Durdurma kontrolü
                return
                
            if self.delay > 0:
                time.sleep(self.delay)  # Belirlenen süre kadar bekle
                
            wallet = self.generate_wallet()
            
            if self.test_mode:
                wallet['balance'] = 0.1 if hash(wallet['address']) % 100 == 0 else 0
            else:
                wallet['balance'] = float(self.check_balance(wallet['address']))
            
            # İlerleme göstergesi
            if self.wallet_limit:
                progress = (self.total_generated / self.wallet_limit) * 100
                print(f"\rİlerleme: {progress:.1f}% ({self.total_generated}/{self.wallet_limit})", end="")
            
            # Ekran çıktısı
            print(self.display_format.format(
                self.total_generated,
                wallet['address'],
                f"{wallet['balance']:.8f} ETH",
                wallet['seed_phrase']
            ))

            # Log girişi hazırla
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entries.append(f"{timestamp},{wallet['address']},{wallet['seed_phrase']},{wallet['balance']}\n")
            
            if wallet['balance'] > 0:
                wallet['found_at'] = datetime.now().isoformat()
                self.found_wallets.append(wallet)
                print(f"\n💰 BAKİYELİ CÜZDAN BULUNDU! Adres: {wallet['address']}, Bakiye: {wallet['balance']} ETH\n")
            
            wallets.append(wallet)
        
        # Toplu kayıt işlemleri
        if wallets:
            self.save_wallet_batch(wallets)
        if log_entries:
            self.log_wallet_batch(log_entries)
    
    def calculate_speed(self):
        """Cüzdan üretim hızını hesaplar"""
        if not self.start_time or self.total_generated == 0:
            return 0
        elapsed_seconds = (datetime.now() - self.start_time).total_seconds()
        return self.total_generated / elapsed_seconds if elapsed_seconds > 0 else 0
        
    def print_stats(self):
        """İstatistikleri yazdırır"""
        if self.total_generated == 0:
            return  # Henüz cüzdan üretilmemişse istatistik gösterme
            
        current_time = datetime.now()
        elapsed_time = current_time - self.start_time
        speed = self.calculate_speed()
        total_seconds = int(elapsed_time.total_seconds())
        
        print("\n" + "=" * 50)
        print(f"📊 PERFORMANS İSTATİSTİKLERİ")
        print("=" * 50)
        print(f"⏱️  Geçen süre: {str(timedelta(seconds=total_seconds))}")
        print(f"📈 Toplam üretilen: {self.total_generated} cüzdan")
        print(f"⚡ Hız: {speed:.2f} cüzdan/saniye")
        
        if self.total_generated > 0:
            print(f"💡 Ortalama: {(total_seconds/self.total_generated):.2f} saniye/cüzdan")
        
        print(f"💰 Bakiyeli bulunan: {len(self.found_wallets)} cüzdan")
        print(f"📝 Log dosyası: {self.log_file}")
        print("=" * 50 + "\n")

    def check_stop_key(self):
        """S tuşuna basılınca programı durdurur"""
        print("\nProgramı durdurmak için 'S' tuşuna basın...")
        
        if os.name == 'nt':  # Windows
            while self.running:
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8').lower()
                    if key == 's':
                        print("\n⚠️ S tuşuna basıldı. Program kapatılıyor...")
                        self.running = False
                        break
                time.sleep(0.1)
        else:  # Unix sistemler için
            old_settings = termios.tcgetattr(sys.stdin)
            try:
                tty.setcbreak(sys.stdin.fileno())
                while self.running:
                    if sys.stdin.read(1).lower() == 's':
                        print("\n⚠️ S tuşuna basıldı. Program kapatılıyor...")
                        self.running = False
                        break
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def run(self, num_threads=4):
        """Ana çalıştırma fonksiyonu"""
        print(f"{'TEST MODUNDA ' if self.test_mode else ''}Ethereum cüzdan taraması başlatılıyor...")
        if self.wallet_limit:
            print(f"Hedef cüzdan sayısı: {self.wallet_limit}")
        
        self.start_time = datetime.now()
        self.last_stat_time = self.start_time
        
        # Thread havuzu optimizasyonu
        optimal_threads = min(32, os.cpu_count() * 2) if num_threads == 4 else num_threads
        
        with ThreadPoolExecutor(max_workers=optimal_threads) as executor:
            # Stop thread'i başlat
            stop_thread = threading.Thread(target=self.check_stop_key)
            stop_thread.daemon = True
            stop_thread.start()
            
            futures = set()
            remaining = self.wallet_limit if self.wallet_limit else float('inf')
            
            try:
                while (remaining > 0 if self.wallet_limit else True) and self.running:
                    # Mevcut batch'i process et
                    batch_size = min(self.batch_size, remaining if self.wallet_limit else self.batch_size)
                    future = executor.submit(self.process_wallet_batch, batch_size)
                    futures.add(future)
                    
                    if self.wallet_limit:
                        remaining -= batch_size
                    
                    # Tamamlanan işlemleri bekle ve temizle
                    completed = set()
                    for f in futures:
                        if f.done():
                            try:
                                f.result()  # Hataları yakala
                                completed.add(f)
                            except Exception as e:
                                print(f"İşlem hatası: {e}")
                    
                    futures -= completed
                    
                    # İstatistikleri göster
                    if self.total_generated > 0 and self.total_generated % self.batch_size == 0:
                        self.print_stats()
                    
                    # İşlem sayısını kontrol et ve bekle
                    while len(futures) >= optimal_threads and self.running:
                        time.sleep(0.1)
                        
                        # Tamamlananları temizle
                        completed = {f for f in futures if f.done()}
                        for f in completed:
                            try:
                                f.result()
                            except Exception as e:
                                print(f"İşlem hatası: {e}")
                        futures -= completed
                        
            except KeyboardInterrupt:
                print("\n\n⚠️ Durdurma sinyali alındı...")
                self.running = False
                
            finally:
                print("\nİşlemler durduruluyor...")
                # Bekleyen işlemleri iptal et
                for future in futures:
                    future.cancel()
                
                # Tamamlanan son işlemleri bekle
                for future in futures:
                    if not future.cancelled():
                        try:
                            future.result(timeout=1)
                        except:
                            pass
                
                # Thread'i temiz bir şekilde kapat
                self.running = False
                if stop_thread.is_alive():
                    stop_thread.join(timeout=1)
                
                print("\n🛑 Program durduruldu.")
                self.print_final_stats()

    def print_final_stats(self):
        """Final istatistiklerini yazdırır"""
        elapsed_time = datetime.now() - self.start_time
        speed = self.calculate_speed()
        total_seconds = int(elapsed_time.total_seconds())
        
        print("\n" + "=" * 50)
        print(f"📊 TARAMA SONUÇLARI")
        print("=" * 50)
        print(f"⏱️  Toplam süre: {str(timedelta(seconds=total_seconds))}")
        print(f"📈 Üretilen cüzdan: {self.total_generated} adet")
        print(f"⚡ Ortalama hız: {speed:.2f} cüzdan/saniye")
        print(f"💰 Bakiyeli bulunan: {len(self.found_wallets)} cüzdan")
        print(f"📝 Log dosyası: {self.log_file}")
        if self.found_wallets:
            print("\n💎 BULUNAN BAKİYELİ CÜZDANLAR:")
            for wallet in self.found_wallets:
                print(f"   Adres: {wallet['address']}")
                print(f"   Bakiye: {wallet['balance']} ETH")
                print(f"   Seed: {wallet['seed_phrase']}")
                print("   " + "-" * 40)
        print("=" * 50)

def main():
    parser = argparse.ArgumentParser(description='Ethereum Cüzdan Bulucu')
    parser.add_argument('--test', action='store_true', help='Test modunda çalıştır')
    parser.add_argument('--output', type=str, default='wallets.json', help='Çıktı dosyası')
    parser.add_argument('--threads', type=int, default=4, help='İş parçacığı sayısı')
    parser.add_argument('--limit', type=int, help='Üretilecek cüzdan sayısı')
    parser.add_argument('--save', action='store_true', help='Taranan cüzdanları kaydet')  # Yeni parametre
    parser.add_argument('--delay', type=float, default=0, 
                       help='Her cüzdan üretimi arasındaki bekleme süresi (saniye)')
    
    args = parser.parse_args()
    
    if not args.limit:
        try:
            args.limit = int(input("Kaç adet cüzdan üretmek istiyorsunuz? (Limitsiz için 0): "))
        except ValueError:
            print("Geçersiz sayı, limitsiz devam ediliyor...")
            args.limit = None
            
    if args.limit == 0:
        args.limit = None
        
    generator = EthereumWalletGenerator(
        output_file=args.output, 
        test_mode=args.test,
        wallet_limit=args.limit,
        save_wallets=args.save,  # Yeni parametre aktarımı
        delay=args.delay  # Yeni: delay parametresi aktarımı
    )
    generator.run(num_threads=args.threads)

if __name__ == "__main__":
    main()
``` 