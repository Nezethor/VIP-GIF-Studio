import os
import subprocess

def compile_inno_setup():
    iscc_path = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    iss_script = "installer.iss"

    if not os.path.exists(iscc_path):
        print(f"❌ No se encontró ISCC.exe en {iscc_path}")
        return False

    if not os.path.exists(iss_script):
        print(f"❌ No se encontró {iss_script}")
        return False

    print("==================================================")
    print(" Compilando Instalador de Windows con Inno Setup 6")
    print("==================================================")

    res = subprocess.run([iscc_path, iss_script])
    if res.returncode == 0:
        print("\n==================================================")
        print(" ¡Instalador compilado exitosamente!")
        print(" Archivo generado en: installer_dist/VIP_GIF_Studio_Setup_v2.6.0.exe")
        print("==================================================")
        return True
    else:
        print("❌ Error al compilar con Inno Setup.")
        return False

if __name__ == "__main__":
    compile_inno_setup()
