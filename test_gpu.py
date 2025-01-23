import sys
import platform
import numpy as np
from numba import cuda, __version__ as numba_version
import ctypes
import os
from subprocess import check_output, CalledProcessError, DEVNULL

def get_package_version(package_name):
    try:
        return pkg_resources.get_distribution(package_name).version
    except pkg_resources.DistributionNotFound:
        return "not installed"

def get_nvidia_details():
    """NVIDIA sürücü bilgilerini detaylı kontrol et"""
    try:
        if platform.system() == 'Windows':
            try:
                # nvidia-smi ile detaylı kontrol
                output = check_output(['nvidia-smi'], stderr=DEVNULL).decode()
                return "NVIDIA sürücüsü yüklü: " + output.split('\n')[0]
            except CalledProcessError:
                # Registry kontrolü
                import winreg
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                        r"SOFTWARE\NVIDIA Corporation\Global") as key:
                        return "NVIDIA sürücüsü yüklü (nvidia-smi bulunamadı)"
                except WindowsError:
                    pass
                
            # Device Manager kontrolü
            try:
                output = check_output('wmic path win32_VideoController get name', shell=True).decode()
                if 'NVIDIA' in output:
                    return f"NVIDIA GPU bulundu: {output.split('Name')[1].strip()}"
            except:
                pass
                
            return "NVIDIA sürücüsü bulunamadı"
        else:
            # Linux için lspci kontrolü
            try:
                output = check_output(['lspci', '|', 'grep', '-i', 'nvidia'], shell=True).decode()
                return f"NVIDIA GPU bulundu: {output.strip()}"
            except:
                return "NVIDIA sürücüsü bulunamadı"
    except Exception as e:
        return f"Sürücü kontrolünde hata: {str(e)}"

def get_gpu_memory():
    """GPU bellek bilgisini al"""
    try:
        if platform.system() == 'Windows':
            cmd = 'nvidia-smi --query-gpu=memory.total --format=csv,nounits,noheader'
            try:
                memory = check_output(cmd, shell=True).decode().strip()
                return int(memory)
            except:
                return None
    except:
        return None
    return None

def test_gpu():
    print("CUDA sistemi kontrol ediliyor...\n")
    
    try:
        # Sistem bilgilerini göster
        print("=== Sistem Bilgileri ===")
        print(f"OS: {platform.system()} {platform.release()}")
        print(f"Python: {sys.version.split()[0]}")
        print(f"NumPy: {np.__version__}")
        print(f"Numba: {numba_version}")
        
        # NVIDIA durumunu kontrol et
        nvidia_status = get_nvidia_details()
        print(f"NVIDIA Durumu: {nvidia_status}")
        
        # CUDA path kontrolü
        cuda_path = os.environ.get('CUDA_PATH')
        if cuda_path:
            print(f"CUDA Path: {cuda_path}")
        else:
            print("CUDA Path bulunamadı!")
        
        # CUDA kullanılabilirliğini detaylı kontrol et
        if not cuda.is_available():
            cuda_err = "Bilinmeyen hata"
            try:
                cuda.current_context()
            except cuda.cudadrv.error.CudaSupportError as e:
                cuda_err = f"CUDA sürücü hatası: {str(e)}"
            except cuda.cudadrv.error.CudaDriverError as e:
                cuda_err = f"CUDA sürücü hatası: {str(e)}"
            except Exception as e:
                cuda_err = str(e)
                
            raise RuntimeError(f"CUDA kullanılamıyor: {cuda_err}")
            
        # GPU bilgilerini göster
        device = cuda.get_current_device()
        print("\n=== GPU Bilgileri ===")
        print(f"GPU: {device.name}")
        print(f"CUDA Driver Version: {cuda.runtime.get_version()}")
        print(f"Compute Capability: {device.compute_capability}")
        print(f"Max Threads Per Block: {device.MAX_THREADS_PER_BLOCK}")
        print(f"Max Block Dimensions: {device.MAX_BLOCK_DIM_X}, {device.MAX_BLOCK_DIM_Y}, {device.MAX_BLOCK_DIM_Z}")
        
        # GPU bellek bilgisini al
        memory = get_gpu_memory()
        if memory:
            print(f"Memory Size: {memory / 1024:.2f} GB")
        else:
            print("Memory Size: Bilgi alınamadı")

        # Test kernel oluştur ve çalıştır
        @cuda.jit
        def test_kernel(arr):
            idx = cuda.grid(1)
            if idx < arr.size:
                arr[idx] *= 2
                
        # Test verisi oluştur - boyutu artırıyoruz
        data = np.array(range(1, 1025), dtype=np.float32)  # 1024 eleman
        d_data = cuda.to_device(data)
        
        # Kernel çalıştırma parametrelerini optimize et
        threads_per_block = 256  # GPU'nun max thread sayısına göre optimal
        blocks = (data.size + threads_per_block - 1) // threads_per_block
        # En az 2 blok kullanılmasını sağla
        blocks = max(2, blocks)
        
        # Kernel'i çalıştır
        test_kernel[blocks, threads_per_block](d_data)
        
        result = d_data.copy_to_host()
        print("\n=== Test Sonucu ===")
        print("GPU test başarılı!")
        print(f"Test konfigürasyonu:")
        print(f"- Veri boyutu: {data.size} eleman")
        print(f"- Thread/Block: {threads_per_block}")
        print(f"- Blok sayısı: {blocks}")
        print(f"Test örneği (ilk 5 eleman):")
        print(f"Girdi: {data[:5]}")
        print(f"Çıktı: {result[:5]}")
        
    except RuntimeError as e:
        print(f"\nGPU test hatası: {e}")
        print("\nÇözüm önerileri:")
        print("1. NVIDIA GPU'nuz olduğundan emin olun")
        print("   - GPU modeli kontrol: Windows -> Aygıt Yöneticisi -> Ekran Bağdaştırıcıları")
        print("   - Linux: lspci | grep -i nvidia")
        print("\n2. NVIDIA sürücülerini güncelleyin")
        print("   Windows: https://www.nvidia.com/Download/index.aspx")
        print("   Linux: sudo apt update && sudo apt install nvidia-driver-xxx")
        print("\n3. CUDA Toolkit'i kurun:")
        print("   https://developer.nvidia.com/cuda-downloads")
        print("   - Kurulumdan sonra sistemi yeniden başlatın")
        print("   - Path değişkenlerini kontrol edin")
        print("\n4. Python paketlerini güncelleyin:")
        print("   pip install --upgrade numba numpy cuda-python")
        print("\nSistem Gereksinimleri:")
        print(f"- Python: 3.7 veya üstü (Mevcut: {sys.version.split()[0]})")
        print(f"- Numba: 0.57 veya üstü (Mevcut: {numba_version})")
        print(f"- NumPy: 1.20 veya üstü (Mevcut: {np.__version__})")
        print("\nEk Kontroller:")
        print("1. CUDA_PATH çevre değişkenini kontrol edin")
        print("2. NVIDIA sürücülerini kaldırıp yeniden kurun")
        print("3. Visual Studio C++ Runtime yüklü olduğundan emin olun")
        print("4. NVIDIA GPU'nun CUDA desteğini kontrol edin:")
        print("   https://developer.nvidia.com/cuda-gpus")
        raise

if __name__ == "__main__":
    test_gpu()
