import os
import sys
import subprocess
import imageio_ffmpeg

def build():
    print("==================================================")
    print("   Compilando VIP GIF Studio v1.0.0 a .EXE ...")
    print("==================================================")

    ffmpeg_bin_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    print(f"Ruta de binarios FFmpeg detectada: {ffmpeg_bin_dir}")

    # Build PyInstaller command
    add_data_param = f"{ffmpeg_bin_dir};imageio_ffmpeg/binaries"
    icon_param = os.path.abspath(os.path.join("assets", "icon.ico"))
    add_assets = f"{os.path.abspath('assets')};assets"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--icon", icon_param,
        "--name", "VIP_GIF_Studio_v1.7.1",
        "--add-data", add_data_param,
        "--add-data", add_assets,
        "--hidden-import", "PyQt6",
        "--hidden-import", "cv2",
        "--hidden-import", "PIL",
        "--hidden-import", "imageio_ffmpeg",
        "main.pyw"
    ]

    print(f"Ejecutando comando: {' '.join(cmd)}")
    res = subprocess.run(cmd)

    if res.returncode == 0:
        print("\n==================================================")
        print(" ¡Compilación completada con éxito!")
        print(" Ejecutable generado en: dist/VIP_GIF_Studio_v1.0.0.exe")
        print("==================================================")
    else:
        print("\n❌ Error durante la compilación con PyInstaller.")

if __name__ == "__main__":
    build()
