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
import signal
import sys
import threading

if os.name == 'nt':
    import msvcrt
else:
    import tty
    import termios

Account.enable_unaudited_hdwallet_features()

w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/apiid'))

class EthereumWalletGenerator:
    def __init__(self, output_file="wallets.json", test_mode=False, wallet_limit=None, save_wallets=False, delay=0):
        self.output_file = output_file
        self.test_mode = test_mode
        self.found_wallets = []
        self.total_generated = 0
        self.wallet_limit = wallet_limit
        self.start_time = None
        self.last_stat_time = None
        self.display_format = "%-4d | %-42s | %-20s | %-90s"
        self.mnemo = Mnemonic("english")
        self.save_wallets = save_wallets
        self.delay = delay
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = "wallet_scan_%s.log" % timestamp
        print("Log dosyasi: %s" % self.log_file)
        
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("Timestamp,Address,Seed Phrase,Balance\n")
        
        print("\n" + "%-4s | %-42s | %-20s | %-90s" % ("SIRA", "ADRES", "BAKIYE", "SEED PHRASE"))
        print("-" * 160)
        
        self.wallet_queue = Queue(maxsize=1000)
        self.log_lock = Lock()
        self.save_lock = Lock()
        self.batch_size = 1
        self.wallet_buffer = []
        self.running = True
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        print("\n\nDurdurma sinyali alindi. Program guvenli bir sekilde sonlandiriliyor...")
        self.running = False
        
    def generate_wallet(self):
        mnemonic = self.mnemo.generate(strength=128)
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
        try:
            time.sleep(0.5)
            balance = w3.eth.get_balance(address)
            return w3.from_wei(balance, 'ether')
        except Exception as e:
            print("Hata: %s" % e)
            return 0
    
    def save_wallet_batch(self, wallets):
        if not self.save_wallets:
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
                print("Toplu kayit hatasi: %s" % e)

    def log_wallet_batch(self, entries):
        with self.log_lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.writelines(entries)

    def process_wallet_batch(self, size=1):
        wallets = []
        log_entries = []
        
        for _ in range(size):
            if not self.running:
                return
                
            if self.delay > 0:
                time.sleep(self.delay)
                
            wallet = self.generate_wallet()
            
            if self.test_mode:
                wallet['balance'] = 0.1 if hash(wallet['address']) % 100 == 0 else 0
            else:
                wallet['balance'] = float(self.check_balance(wallet['address']))
            
            if self.wallet_limit:
                progress = (self.total_generated / self.wallet_limit) * 100
                sys.stdout.write("\rIlerleme: %.1f%% (%d/%d)                    " % (progress, self.total_generated, self.wallet_limit))
                sys.stdout.flush()
            
            print("\n%-4d | %-42s | %-20s | %-90s" % (
                self.total_generated,
                wallet['address'],
                "%.8f ETH" % wallet['balance'],
                wallet['seed_phrase']
            ))

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entries.append("%s,%s,%s,%s\n" % (timestamp, wallet['address'], wallet['seed_phrase'], wallet['balance']))
            
            if wallet['balance'] > 0:
                wallet['found_at'] = datetime.now().isoformat()
                self.found_wallets.append(wallet)
                print("\nBAKIYELI CUZDAN BULUNDU! Adres: %s, Bakiye: %.8f ETH\n" % (wallet['address'], wallet['balance']))
            
            wallets.append(wallet)
        
        if wallets:
            self.save_wallet_batch(wallets)
        if log_entries:
            self.log_wallet_batch(log_entries)
    
    def calculate_speed(self):
        if not self.start_time or self.total_generated == 0:
            return 0
        elapsed_seconds = (datetime.now() - self.start_time).total_seconds()
        return self.total_generated / elapsed_seconds if elapsed_seconds > 0 else 0
        
    def print_stats(self):
        if self.total_generated == 0:
            return
            
        current_time = datetime.now()
        elapsed_time = current_time - self.start_time
        speed = self.calculate_speed()
        total_seconds = int(elapsed_time.total_seconds())
        
        print("\n" + "=" * 50)
        print("PERFORMANS ISTATISTIKLERI")
        print("=" * 50)
        print("Gecen sure: %s" % str(timedelta(seconds=total_seconds)))
        print("Toplam uretilen: %d cuzdan" % self.total_generated)
        print("Hiz: %.2f cuzdan/saniye" % speed)
        
        if self.total_generated > 0:
            print("Ortalama: %.2f saniye/cuzdan" % (total_seconds/self.total_generated))
        
        print("Bakiyeli bulunan: %d cuzdan" % len(self.found_wallets))
        print("Log dosyasi: %s" % self.log_file)
        print("=" * 50 + "\n")

    def run(self, num_threads=4):
        print("%sEthereum cuzdan taramasi baslatiliyor..." % ('TEST MODUNDA ' if self.test_mode else ''))
        if self.wallet_limit:
            print("Hedef cuzdan sayisi: %d" % self.wallet_limit)
        
        self.start_time = datetime.now()
        self.last_stat_time = self.start_time
        
        optimal_threads = min(32, os.cpu_count() * 2) if num_threads == 4 else num_threads
        
        with ThreadPoolExecutor(max_workers=optimal_threads) as executor:
            futures = set()
            remaining = self.wallet_limit if self.wallet_limit else float('inf')
            
            try:
                while (remaining > 0 if self.wallet_limit else True) and self.running:
                    batch_size = min(self.batch_size, remaining if self.wallet_limit else self.batch_size)
                    future = executor.submit(self.process_wallet_batch, batch_size)
                    futures.add(future)
                    
                    if self.wallet_limit:
                        remaining -= batch_size
                    
                    completed = {f for f in futures if f.done()}
                    for f in completed:
                        try:
                            f.result()
                        except Exception as e:
                            print("Islem hatasi: %s" % e)
                    futures -= completed
                    
                    time.sleep(0.1)
                
                wait(futures)
                
                self.print_stats()
                
            except KeyboardInterrupt:
                print("\n\nDurdurma sinyali alindi...")
                self.running = False
                self.print_stats()
                
            finally:
                print("\nIslemler durduruluyor...")
                for future in futures:
                    future.cancel()
                
                for future in futures:
                    if not future.cancelled():
                        try:
                            future.result(timeout=1)
                        except:
                            pass
                
                self.running = False
                print("\nProgram durduruldu.")
                self.print_final_stats()

    def print_final_stats(self):
        elapsed_time = datetime.now() - self.start_time
        speed = self.calculate_speed()
        total_seconds = int(elapsed_time.total_seconds())
        
        print("\n" + "=" * 50)
        print("TARAMA SONUCLARI")
        print("=" * 50)
        print("Toplam sure: %s" % str(timedelta(seconds=total_seconds)))
        print("Uretilen cuzdan: %d adet" % self.total_generated)
        print("Ortalama hiz: %.2f cuzdan/saniye" % speed)
        print("Bakiyeli bulunan: %d cuzdan" % len(self.found_wallets))
        print("Log dosyasi: %s" % self.log_file)
        if self.found_wallets:
            print("\nBULUNAN BAKIYELI CUZDANLAR:")
            for wallet in self.found_wallets:
                print("   Adres: %s" % wallet['address'])
                print("   Bakiye: %.8f ETH" % wallet['balance'])
                print("   Seed: %s" % wallet['seed_phrase'])
                print("   " + "-" * 40)
        print("=" * 50)

def main():
    parser = argparse.ArgumentParser(description='Ethereum Cuzdan Bulucu')
    parser.add_argument('--test', action='store_true', help='Test modunda calistir')
    parser.add_argument('--output', type=str, default='wallets.json', help='Cikti dosyasi')
    parser.add_argument('--threads', type=int, default=4, help='Is parcacigi sayisi')
    parser.add_argument('--limit', type=int, help='Uretilecek cuzdan sayisi')
    parser.add_argument('--save', action='store_true', help='Taranan cuzdanlari kaydet')
    parser.add_argument('--delay', type=float, default=0, 
                       help='Her cuzdan uretimi arasindaki bekleme suresi (saniye)')
    
    args = parser.parse_args()
    
    if not args.limit:
        try:
            args.limit = int(input("Kac adet cuzdan uretmek istiyorsunuz? (Limitsiz icin 0): "))
        except ValueError:
            print("Gecersiz sayi, limitsiz devam ediliyor...")
            args.limit = None
            
    if args.limit == 0:
        args.limit = None
        
    generator = EthereumWalletGenerator(
        output_file=args.output, 
        test_mode=args.test,
        wallet_limit=args.limit,
        save_wallets=args.save,
        delay=args.delay
    )
    generator.run(num_threads=args.threads)

if __name__ == "__main__":
    main() 
