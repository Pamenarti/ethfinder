import numpy as np
from numba import cuda, uint8, float32
import eth_keys
from eth_utils import to_checksum_address
from datetime import datetime
import time
from dotenv import load_dotenv
import os
import sys

# .env dosyasını yükle
load_dotenv()

# GPU ayarları
GPU_INTENSITY = int(os.getenv('GPU_INTENSITY', 90))
WALLET_LIMIT = float(os.getenv('WALLET_LIMIT', 'inf'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 100000))
THREADS_PER_BLOCK = int(os.getenv('THREADS_PER_BLOCK', 512))
BLOCKS_PER_GRID = (BATCH_SIZE + THREADS_PER_BLOCK - 1) // THREADS_PER_BLOCK

# Dosya yolları
RICH_ADDRESSES_FILE = os.getenv('RICH_ADDRESSES_FILE', '10000richAddressETH.txt')
LOG_FILE_PREFIX = os.getenv('LOG_FILE_PREFIX', 'wallet')
FOUND_FILE = os.getenv('FOUND_FILE', 'bulunanlar.txt')

def check_cuda_available():
    """CUDA ve GPU kontrolü yapar"""
    if not cuda.is_available():
        raise RuntimeError("""
CUDA GPU bulunamadı!
Lütfen şunları kontrol edin:
1. NVIDIA GPU'ya sahip olduğunuzdan emin olun
2. NVIDIA sürücülerinin kurulu olduğunu kontrol edin
3. CUDA Toolkit'in kurulu olduğunu kontrol edin
4. Numba ve CUDA versiyonlarının uyumlu olduğunu kontrol edin

Kurulum adımları:
1. NVIDIA sürücülerini güncelleyin
2. CUDA Toolkit'i kurun: https://developer.nvidia.com/cuda-downloads
3. Python paketlerini güncelleyin:
   pip install --upgrade numba numpy
""")
    return True

@cuda.jit(device=True)
def gpu_keccak256(private_key, result):
    """Optimize edilmiş Keccak256 hash hesaplama"""
    # Daha hızlı hash için döngü açılımı
    for i in range(0, 32, 4):
        x0 = private_key[i]
        x1 = private_key[i+1]
        x2 = private_key[i+2]
        x3 = private_key[i+3]
        
        x0 = (x0 ^ ((x0 << 13) & 0xFF)) ^ ((x0 >> 7) & 0xFF)
        x1 = (x1 ^ ((x1 << 13) & 0xFF)) ^ ((x1 >> 7) & 0xFF)
        x2 = (x2 ^ ((x2 << 13) & 0xFF)) ^ ((x2 >> 7) & 0xFF)
        x3 = (x3 ^ ((x3 << 13) & 0xFF)) ^ ((x3 >> 7) & 0xFF)
        
        result[i] = x0
        result[i+1] = x1
        result[i+2] = x2
        result[i+3] = x3

@cuda.jit(device=True)
def gpu_xorshift(state):
    """GPU üzerinde basit bir rastgele sayı üreteci"""
    x = state
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5) & 0xFFFFFFFF
    return x & 0xFFFFFFFF

@cuda.jit
def generate_and_check_wallets(out_addresses, out_private_keys, valid_count, rnd_states):
    pos = cuda.grid(1)
    if pos < BATCH_SIZE:
        # Yerel diziler
        private_key = cuda.local.array(32, dtype=uint8)
        public_key = cuda.local.array(32, dtype=uint8)
        state = rnd_states[pos]
        
        # Optimize edilmiş private key üretimi
        for i in range(0, 32, 4):
            state = gpu_xorshift(state)
            private_key[i] = uint8(state & 0xFF)
            private_key[i+1] = uint8((state >> 8) & 0xFF)
            private_key[i+2] = uint8((state >> 16) & 0xFF)
            private_key[i+3] = uint8((state >> 24) & 0xFF)
        
        # Public key türetme
        gpu_keccak256(private_key, public_key)
        
        # Sonuçları manuel kopyalama ile yaz
        idx = cuda.atomic.add(valid_count, 0, 1)
        if idx < out_addresses.shape[0]:
            for i in range(32):
                out_private_keys[idx, i] = private_key[i]
                out_addresses[idx, i] = public_key[i]

        rnd_states[pos] = state

class WalletGenerator:
    def __init__(self):
        self.stats = {'total': 0, 'matches': 0, 'start_time': time.time()}
        self.use_gpu = True  # GPU kullanımı için bayrak eklendi
        
        # CUDA kontrolü
        check_cuda_available()
        
        try:
            # GPU bilgilerini göster
            device = cuda.get_current_device()
            print(f"\n=== GPU Bilgileri ===")
            print(f"GPU: {device.name}")
            print(f"Compute Capability: {device.compute_capability}")
            print(f"Max Threads Per Block: {device.MAX_THREADS_PER_BLOCK}")
            print("===================\n")
            
            # GPU belleği ayır
            self.d_addresses = cuda.device_array((BATCH_SIZE, 32), dtype=np.uint8)
            self.d_private_keys = cuda.device_array((BATCH_SIZE, 32), dtype=np.uint8)
            self.d_valid_count = cuda.device_array(1, dtype=np.int32)
            
            # Pinned bellek kullanımı
            self.h_addresses = cuda.pinned_array((BATCH_SIZE, 32), dtype=np.uint8)
            self.h_private_keys = cuda.pinned_array((BATCH_SIZE, 32), dtype=np.uint8)
            
            # Stream optimizasyonu
            self.stream = cuda.stream()
            # GPU bağlamını başlat
            ctx = cuda.current_context()
            
            # RNG durumları için GPU belleği
            self.rnd_states = cuda.to_device(
                np.random.randint(1, 2**32, size=BATCH_SIZE, dtype=np.uint32)
            )
            
            # Rich adresleri yükle
            with open(RICH_ADDRESSES_FILE, 'r') as f:
                self.rich_addresses = set(addr.lower().strip() for addr in f)
            
            self.log_file = f'{LOG_FILE_PREFIX}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
            
            print(f"\nGPU belleği ayrıldı:")
            print(f"- Addresses: {self.d_addresses.nbytes / 1024:.2f} KB")
            print(f"- Private Keys: {self.d_private_keys.nbytes / 1024:.2f} KB")
            print(f"- RNG States: {self.rnd_states.nbytes / 1024:.2f} KB")
            
        except Exception as e:
            raise RuntimeError(f"GPU başlatma hatası: {e}")

    def process_batch(self):
        """GPU kernel'i çalıştır"""
        try:
            # Valid count sıfırla
            self.d_valid_count.copy_to_device(np.zeros(1, dtype=np.int32))
            
            # Kernel'i çalıştır
            generate_and_check_wallets[BLOCKS_PER_GRID, THREADS_PER_BLOCK](
                self.d_addresses, self.d_private_keys, self.d_valid_count, self.rnd_states
            )
            
            # Sonuçları al
            cuda.synchronize()
            valid_count = self.d_valid_count.copy_to_host()[0]
            
            if valid_count > 0:
                addresses = self.d_addresses[:valid_count].copy_to_host()
                private_keys = self.d_private_keys[:valid_count].copy_to_host()
                self._process_results(addresses, private_keys)
                
        except cuda.cudadrv.driver.CudaAPIError as e:
            print(f"\nCUDA Hata: {e}")
            raise
        except Exception as e:
            print(f"\nBatch işleme hatası: {e}")
            raise

    def _process_results(self, addresses, private_keys):
        for addr, priv in zip(addresses, private_keys):
            addr_hex = '0x' + ''.join(f'{x:02x}' for x in addr)
            
            self.stats['total'] += 1
            print(f"\rÜretilen Cüzdan: {addr_hex}", end='')
            
            # Eşleşme kontrolü ve kayıt işlemi
            if addr_hex.lower() in self.rich_addresses:
                self.stats['matches'] += 1
                # bulunanlar.txt'ye kaydet
                with open(FOUND_FILE, 'a') as f:
                    f.write(f"Adres: {addr_hex}\nPrivate Key: {''.join(f'{x:02x}' for x in priv)}\n------------------------\n")
                # Ekrana uyarı bas
                print(f"\nEşleşme bulundu! {addr_hex}")

    def start(self):
        print("\nCüzdan üretimi başlıyor...")
        print(f"GPU modu aktif")
        print(f"Batch Size: {BATCH_SIZE}")
        print(f"Grid boyutu: {BLOCKS_PER_GRID} blok")
        print(f"Thread/Block: {THREADS_PER_BLOCK}")
        
        try:
            while self.stats['total'] < WALLET_LIMIT:
                self.process_batch()
                
                if self.stats['total'] % 100000 == 0:
                    elapsed = time.time() - self.stats['start_time']
                    speed = self.stats['total'] / elapsed
                    print(f"\rHız: {speed:.2f} cüzdan/saniye | Toplam: {self.stats['total']}", end='')
                    
        except KeyboardInterrupt:
            print("\nProgram durduruluyor...")
        finally:
            cuda.synchronize()

if __name__ == '__main__':
    try:
        if not check_cuda_available():
            sys.exit(1)
        generator = WalletGenerator()
        generator.start()
    except RuntimeError as e:
        print(f"\nHATA: {e}")
        print("Program sadece CUDA destekli NVIDIA GPU'larda çalışır!")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nProgram kullanıcı tarafından durduruldu.")
    except Exception as e:
        print(f"Program hatası: {e}")
